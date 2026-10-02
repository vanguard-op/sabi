import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/connectivity.dart';
import '../../data/providers.dart';
import '../../l10n/sab_strings.dart';
import '../../models/intent_result.dart';
import '../../models/receipt_summary.dart';
import '../../models/service_summary.dart';

/// The Home conversation states from screens.md (screen 3). `idle` is the
/// neutral state before any request, `queued` is a request captured offline,
/// `composing` covers a request in flight, and the rest render a resolved
/// result, a single clarification, a coverage gap, or a failure.
enum HomePhase { idle, queued, composing, discovery, clarifying, notCovered, error }

/// One exchange in the Home conversation: the user's own words and the
/// assistant's outcome for them. Turns are immutable and appended in time
/// order, so an earlier request and its result stay on screen (screens.md,
/// screen 3, Layout: "a conversation List ... in time order").
@immutable
class ConversationTurn {
  const ConversationTurn({
    required this.request,
    this.phase = HomePhase.composing,
    this.intent,
    this.candidates = const [],
    this.fromSearch = false,
  });

  /// The user's free-form request, verbatim.
  final String request;

  final HomePhase phase;

  /// The structured intent behind a resolved or clarifying result. Null when
  /// the result came straight from a catalogue search.
  final IntentResult? intent;

  /// The selectable discovery results, whether resolved by intent or by search.
  final List<ServiceSummary> candidates;

  /// True when the result came from a catalogue search fallback (FEAT-004)
  /// rather than from intent resolution.
  final bool fromSearch;

  /// True when any discovery result is not currently active, so the surface can
  /// warn before a payment is started (FEAT-004, stale catalogue data).
  bool get hasInactiveCandidate =>
      candidates.any((service) => service.status != 'active');

  ConversationTurn copyWith({
    HomePhase? phase,
    IntentResult? intent,
    List<ServiceSummary>? candidates,
    bool? fromSearch,
  }) => ConversationTurn(
    request: request,
    phase: phase ?? this.phase,
    intent: intent ?? this.intent,
    candidates: candidates ?? this.candidates,
    fromSearch: fromSearch ?? this.fromSearch,
  );
}

/// The Home conversation. An ordered list of [ConversationTurn]s, oldest first.
/// A new request appends a turn; an earlier turn is never discarded, so a
/// provider-picker or navigation round trip leaves the conversation intact.
@immutable
class HomeState {
  const HomeState({this.turns = const []});

  final List<ConversationTurn> turns;

  /// The turn a response is being built for, or the most recent settled turn.
  ConversationTurn? get current => turns.isEmpty ? null : turns.last;

  HomePhase get phase => current?.phase ?? HomePhase.idle;

  /// True while the most recent request is queued for sync (offline).
  bool get queued => current?.phase == HomePhase.queued;

  /// The most recent request, re-run by [HomeController.retry].
  String? get lastRequest => current?.request;

  IntentResult? get intent => current?.intent;

  List<ServiceSummary> get candidates => current?.candidates ?? const [];

  bool get fromSearch => current?.fromSearch ?? false;

  bool get hasInactiveCandidate =>
      candidates.any((service) => service.status != 'active');
}

/// Recent activity for Home, loaded once and refreshable.
final recentReceiptsProvider = FutureProvider<List<ReceiptSummary>>(
  (ref) => ref.watch(receiptRepositoryProvider).recent(),
);

/// The longest request the client will send. The contract bounds the request at
/// 200 characters (C-009/C-010); the composer enforces the same bound so a
/// well-formed request is never sent just to be rejected.
const int homeRequestMaxLength = 200;

/// Drives Home's conversation between idle, queued, composing, discovery,
/// clarifying, not-covered, and error. Every request appends a turn and every
/// turn is preserved, so the conversation builds up in time order.
///
/// Discovery is reached two ways and both render the same selectable results:
/// a resolved intent (FEAT-003/C-009) and, when intent resolution returns no
/// candidate, a catalogue search (FEAT-004/C-010). A coverage miss is stated
/// rather than invented.
class HomeController extends Notifier<HomeState> {
  @override
  HomeState build() => const HomeState();

  /// Submits a free-form request as a new conversation turn.
  ///
  /// Returns the selectable candidates when the caller should act on them
  /// (present the provider picker); null when the state moved to clarifying,
  /// not-covered, queued, or error.
  Future<List<ServiceSummary>?> submit(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return null;

    if (!ref.read(connectivityProvider)) {
      // A queued request is still part of the conversation: it stays on screen
      // with the offline banner explaining why it has not sent yet.
      _append(ConversationTurn(request: trimmed, phase: HomePhase.queued));
      return null;
    }

    // A second submission while a question is on screen is the answer to that
    // question, so the next low-confidence result escalates instead of asking
    // again (MQ-001: exactly one clarifying question). The question itself
    // stays in the conversation as its own turn.
    final answeringQuestion = state.phase == HomePhase.clarifying;

    _append(ConversationTurn(request: trimmed));

    try {
      final intent = await ref
          .read(catalogueRepositoryProvider)
          .resolveIntent(text: trimmed, locale: ref.read(localeProvider));
      return await _settle(
        intent,
        request: trimmed,
        answeringQuestion: answeringQuestion,
      );
    } catch (_) {
      _updateCurrent((turn) => turn.copyWith(phase: HomePhase.error));
      return null;
    }
  }

  Future<List<ServiceSummary>?> _settle(
    IntentResult intent, {
    required String request,
    required bool answeringQuestion,
  }) async {
    if (intent.candidates.isEmpty) {
      // Intent resolution found nothing; search the catalogue directly so a
      // plain service query still reaches discovery (FEAT-004).
      return _searchFallback(request, intent: intent);
    }
    if (intent.needsClarification) {
      if (answeringQuestion) {
        // The one question was already asked and the answer still did not
        // resolve: state the gap and offer search or support (MQ-001).
        _updateCurrent(
          (turn) => turn.copyWith(
            phase: HomePhase.notCovered,
            intent: intent,
            candidates: intent.candidates,
          ),
        );
        return null;
      }
      _updateCurrent(
        (turn) => turn.copyWith(
          phase: HomePhase.clarifying,
          intent: intent,
          candidates: intent.candidates,
        ),
      );
      return null;
    }
    _updateCurrent(
      (turn) => turn.copyWith(
        phase: HomePhase.discovery,
        intent: intent,
        candidates: intent.candidates,
      ),
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
        _updateCurrent(
          (turn) => turn.copyWith(
            phase: HomePhase.discovery,
            candidates: result.results,
            fromSearch: true,
          ),
        );
        return result.results;
      }
    } catch (_) {
      _updateCurrent((turn) => turn.copyWith(phase: HomePhase.error));
      return null;
    }
    // No result and no invention: state that the service is not covered.
    _updateCurrent(
      (turn) => turn.copyWith(
        phase: HomePhase.notCovered,
        intent: intent,
      ),
    );
    return null;
  }

  /// Re-runs the most recent request in place after a failure, keeping the
  /// request turn rather than appending a duplicate.
  Future<void> retry() async {
    final request = state.current?.request;
    if (request == null) return;
    _updateCurrent((turn) => turn.copyWith(phase: HomePhase.composing));
    try {
      final intent = await ref
          .read(catalogueRepositoryProvider)
          .resolveIntent(text: request, locale: ref.read(localeProvider));
      await _settle(intent, request: request, answeringQuestion: false);
    } catch (_) {
      _updateCurrent((turn) => turn.copyWith(phase: HomePhase.error));
    }
  }

  void reset() => state = const HomeState();

  void _append(ConversationTurn turn) {
    state = HomeState(turns: [...state.turns, turn]);
  }

  void _updateCurrent(ConversationTurn Function(ConversationTurn) update) {
    final current = state.current;
    if (current == null) return;
    final turns = [...state.turns];
    turns[turns.length - 1] = update(current);
    state = HomeState(turns: turns);
  }
}

final homeControllerProvider = NotifierProvider<HomeController, HomeState>(
  HomeController.new,
);
