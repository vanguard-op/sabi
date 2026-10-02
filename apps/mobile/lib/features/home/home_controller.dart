import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/connectivity.dart';
import '../../data/providers.dart';
import '../../l10n/sab_strings.dart';
import '../../models/intent_result.dart';
import '../../models/receipt_summary.dart';
import '../../models/service_summary.dart';

/// The Home conversation states from screens.md (screen 3). `idle` is the
/// neutral state, `composing` covers a request in flight, and the rest render a
/// resolved result, a single clarification, a coverage gap, or a failure.
enum HomePhase { idle, composing, discovery, clarifying, notCovered, error }

/// The conversation on Home. A request is preserved across a failure so the
/// retry is the same request, and the candidates are held once so a discovery
/// result survives a rebuild without re-querying.
@immutable
class HomeState {
  const HomeState({
    this.phase = HomePhase.idle,
    this.intent,
    this.candidates = const [],
    this.queued = false,
    this.lastRequest,
    this.fromSearch = false,
    this.clarified = false,
  });

  final HomePhase phase;

  /// The structured intent behind a resolved or clarifying result. Null when the
  /// result came straight from a catalogue search.
  final IntentResult? intent;

  /// The selectable discovery results, whether resolved by intent or by search.
  final List<ServiceSummary> candidates;

  /// A request was accepted while offline and is queued for sync.
  final bool queued;
  final String? lastRequest;

  /// True when the result came from a catalogue search fallback (FEAT-004)
  /// rather than from intent resolution.
  final bool fromSearch;

  /// True once the single clarifying question has been asked for this request.
  final bool clarified;

  /// True when any discovery result is not currently active, so the surface can
  /// warn before a payment is started (FEAT-004, stale catalogue data).
  bool get hasInactiveCandidate =>
      candidates.any((service) => service.status != 'active');

  HomeState copyWith({
    HomePhase? phase,
    IntentResult? intent,
    List<ServiceSummary>? candidates,
    bool? queued,
    String? lastRequest,
    bool? fromSearch,
    bool? clarified,
  }) => HomeState(
    phase: phase ?? this.phase,
    intent: intent ?? this.intent,
    candidates: candidates ?? this.candidates,
    queued: queued ?? this.queued,
    lastRequest: lastRequest ?? this.lastRequest,
    fromSearch: fromSearch ?? this.fromSearch,
    clarified: clarified ?? this.clarified,
  );
}

/// Recent activity for Home, loaded once and refreshable.
final recentReceiptsProvider = FutureProvider<List<ReceiptSummary>>(
  (ref) => ref.watch(receiptRepositoryProvider).recent(),
);

/// The longest request the client will send. The contract bounds the request at
/// 200 characters (C-009/C-010); the composer enforces the same bound so a
/// well-formed request is never sent just to be rejected.
const int homeRequestMaxLength = 200;

/// Drives Home's conversation between idle, composing, discovery, clarifying,
/// not-covered, and error, preserving the request across failures.
///
/// Discovery is reached two ways and both render the same selectable results:
/// a resolved intent (FEAT-003/C-009) and, when intent resolution returns no
/// candidate, a catalogue search (FEAT-004/C-010). A coverage miss is stated
/// rather than invented.
class HomeController extends Notifier<HomeState> {
  @override
  HomeState build() => const HomeState();

  /// Submits a free-form request.
  ///
  /// Returns the selectable candidates when the caller should act on them
  /// (present the provider picker); null when the state moved to clarifying,
  /// not-covered, queued, or error.
  Future<List<ServiceSummary>?> submit(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return null;

    if (!ref.read(connectivityProvider)) {
      state = HomeState(
        phase: HomePhase.idle,
        queued: true,
        lastRequest: trimmed,
      );
      return null;
    }

    // A second submission while a question is on screen is the answer to that
    // question, so the next low-confidence result escalates instead of asking
    // again (MQ-001: exactly one clarifying question).
    final answeringQuestion = state.phase == HomePhase.clarifying;

    state = HomeState(
      phase: HomePhase.composing,
      lastRequest: trimmed,
      clarified: answeringQuestion,
    );

    try {
      final intent = await ref
          .read(catalogueRepositoryProvider)
          .resolveIntent(text: trimmed, locale: ref.read(localeProvider));
      return await _settle(intent, request: trimmed);
    } catch (_) {
      state = HomeState(phase: HomePhase.error, lastRequest: trimmed);
      return null;
    }
  }

  Future<List<ServiceSummary>?> _settle(
    IntentResult intent, {
    required String request,
  }) async {
    if (intent.candidates.isEmpty) {
      // Intent resolution found nothing; search the catalogue directly so a
      // plain service query still reaches discovery (FEAT-004).
      return _searchFallback(request, intent: intent);
    }
    if (intent.needsClarification) {
      if (state.clarified) {
        // The one question was already asked and the answer still did not
        // resolve: state the gap and offer search or support (MQ-001).
        state = HomeState(
          phase: HomePhase.notCovered,
          intent: intent,
          candidates: intent.candidates,
          lastRequest: request,
          clarified: true,
        );
        return null;
      }
      state = HomeState(
        phase: HomePhase.clarifying,
        intent: intent,
        candidates: intent.candidates,
        lastRequest: request,
        clarified: true,
      );
      return null;
    }
    state = HomeState(
      phase: HomePhase.discovery,
      intent: intent,
      candidates: intent.candidates,
      lastRequest: request,
      clarified: state.clarified,
    );
    return intent.candidates;
  }

  Future<List<ServiceSummary>?> _searchFallback(
    String request, {
    required IntentResult intent,
  }) async {
    try {
      final result = await ref
          .read(catalogueRepositoryProvider)
          .search(request);
      if (result.results.isNotEmpty) {
        state = HomeState(
          phase: HomePhase.discovery,
          candidates: result.results,
          lastRequest: request,
          fromSearch: true,
          clarified: state.clarified,
        );
        return result.results;
      }
    } catch (_) {
      state = HomeState(
        phase: HomePhase.error,
        lastRequest: request,
        clarified: state.clarified,
      );
      return null;
    }
    // No result and no invention: state that the service is not covered.
    state = HomeState(
      phase: HomePhase.notCovered,
      intent: intent,
      lastRequest: request,
      clarified: state.clarified,
    );
    return null;
  }

  /// Re-runs the preserved request after a failure.
  Future<void> retry() async {
    final request = state.lastRequest;
    if (request == null) return;
    // A retry after failure is a fresh attempt, not an answer to a question.
    state = HomeState(phase: HomePhase.idle, lastRequest: request);
    await submit(request);
  }

  void reset() => state = const HomeState();
}

final homeControllerProvider = NotifierProvider<HomeController, HomeState>(
  HomeController.new,
);
