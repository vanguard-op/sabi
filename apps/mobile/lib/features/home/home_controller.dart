import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/connectivity.dart';
import '../../data/providers.dart';
import '../../l10n/sab_strings.dart';
import '../../models/intent_result.dart';
import '../../models/receipt_summary.dart';

/// The Home conversation states from screens.md (screen 3).
enum HomePhase { idle, composing, discovery, clarifying, notCovered, error }

@immutable
class HomeState {
  const HomeState({
    this.phase = HomePhase.idle,
    this.intent,
    this.queued = false,
    this.lastRequest,
  });

  final HomePhase phase;
  final IntentResult? intent;

  /// A request was accepted while offline and is queued for sync.
  final bool queued;
  final String? lastRequest;

  HomeState copyWith({
    HomePhase? phase,
    IntentResult? intent,
    bool? queued,
    String? lastRequest,
  }) => HomeState(
    phase: phase ?? this.phase,
    intent: intent ?? this.intent,
    queued: queued ?? this.queued,
    lastRequest: lastRequest ?? this.lastRequest,
  );
}

/// Recent activity for Home, loaded once and refreshable.
final recentReceiptsProvider = FutureProvider<List<ReceiptSummary>>(
  (ref) => ref.watch(receiptRepositoryProvider).recent(),
);

/// Drives Home's conversation between idle, composing, discovery, clarifying,
/// not-covered, and error, preserving the request across failures.
class HomeController extends Notifier<HomeState> {
  @override
  HomeState build() => const HomeState();

  /// Submits a free-form request. Returns the resolved intent when the caller
  /// should act on candidates (navigate or open the provider picker); null when
  /// the state changed to clarifying, not-covered, queued, or error.
  Future<IntentResult?> submit(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return null;

    if (!ref.read(connectivityProvider)) {
      state = const HomeState(phase: HomePhase.idle, queued: true);
      return null;
    }

    state = HomeState(phase: HomePhase.composing, lastRequest: trimmed);
    try {
      final intent = await ref
          .read(catalogueRepositoryProvider)
          .resolveIntent(text: trimmed, locale: ref.read(localeProvider));
      if (intent.candidates.isEmpty) {
        state = HomeState(
          phase: HomePhase.notCovered,
          intent: intent,
          lastRequest: trimmed,
        );
        return null;
      }
      if (intent.needsClarification) {
        state = HomeState(
          phase: HomePhase.clarifying,
          intent: intent,
          lastRequest: trimmed,
        );
        return null;
      }
      state = HomeState(
        phase: HomePhase.discovery,
        intent: intent,
        lastRequest: trimmed,
      );
      return intent;
    } catch (_) {
      state = HomeState(phase: HomePhase.error, lastRequest: trimmed);
      return null;
    }
  }

  Future<void> retry() async {
    final request = state.lastRequest;
    if (request == null) return;
    await submit(request);
  }

  void reset() => state = const HomeState();
}

final homeControllerProvider = NotifierProvider<HomeController, HomeState>(
  HomeController.new,
);
