import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/connectivity.dart';
import '../../data/providers.dart';
import '../../data/repositories.dart';
import '../../l10n/sab_strings.dart';
import '../../models/intent_result.dart';
import '../../models/receipt_summary.dart';
import '../../models/service_summary.dart';

/// The Home conversation states from screens.md (screen 3). `idle` is the
/// neutral state before any request, `queued` is a request captured offline,
/// `composing` covers a request in flight, `conversational` is a non-command
/// message answered in kind, and the rest render a resolved result, a
/// clarification, a coverage gap, or a failure.
enum HomePhase {
  idle,
  queued,
  composing,
  discovery,
  clarifying,
  conversational,
  notCovered,
  error,
}

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

/// How many clarifying questions one conversation may ask before the assistant
/// states the gap and offers catalogue search and human support (FEAT-003,
/// MQ-001). A non-command message never consumes one of these turns.
const int homeClarificationLimit = 3;

/// Drives Home's conversation between idle, queued, composing, discovery,
/// clarifying, conversational, not-covered, and error. Every request appends a
/// turn and every turn is preserved, so the conversation builds up in time
/// order.
///
/// Each resolution carries the prior conversation as C-009 revision 3 `history`
/// so a follow-up builds on the answers already given. Discovery is reached two
/// ways and both render the same selectable results: a resolved intent
/// (FEAT-003/C-009) and, when intent resolution returns no candidate and asks no
/// question, a catalogue search (FEAT-004/C-010). A clarification request from
/// the model is honoured before the search fallback; a non-command message is
/// answered conversationally without being recorded; and once the clarification
/// bound is reached the request is searched and, if still unmatched, stated as a
/// coverage gap rather than guessed.
class HomeController extends Notifier<HomeState> {
  @override
  HomeState build() => const HomeState();

  /// Submits a free-form request as a new conversation turn.
  ///
  /// Returns the selectable candidates when the caller should act on them
  /// (present the provider picker); null when the state moved to clarifying,
  /// conversational, not-covered, queued, or error.
  Future<List<ServiceSummary>?> submit(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return null;

    if (!ref.read(connectivityProvider)) {
      // A queued request is still part of the conversation: it stays on screen
      // with the offline banner explaining why it has not sent yet.
      _append(ConversationTurn(request: trimmed, phase: HomePhase.queued));
      return null;
    }

    _append(ConversationTurn(request: trimmed));

    try {
      final intent = await _resolve(trimmed);
      return await _settle(intent, request: trimmed);
    } catch (_) {
      _updateCurrent((turn) => turn.copyWith(phase: HomePhase.error));
      return null;
    }
  }

  /// Resolves [text] with the conversation so far attached. The in-flight turn
  /// is already on the state, so [_history] drops it and sends only what came
  /// before (C-009 revision 3).
  Future<IntentResult> _resolve(String text) {
    final locale = ref.read(localeProvider);
    final history = _history();
    final Object catalogue = ref.read(catalogueRepositoryProvider);
    if (catalogue is HistoryAwareCatalogueRepository) {
      return catalogue.resolveIntentWithHistory(
        text: text,
        locale: locale,
        history: history,
      );
    }
    return (catalogue as CatalogueRepository).resolveIntent(
      text: text,
      locale: locale,
    );
  }

  /// The prior user and assistant turns, oldest first, bounded to
  /// [intentHistoryMaxEntries]. The in-flight turn (the last one) is excluded.
  List<IntentHistoryTurn> _history() {
    if (state.turns.length <= 1) return const [];
    final strings = ref.read(sabStringsProvider);
    final entries = <IntentHistoryTurn>[];
    for (final turn in state.turns.take(state.turns.length - 1)) {
      entries.add(IntentHistoryTurn(role: 'user', text: turn.request));
      final reply = _assistantReply(turn, strings);
      if (reply != null && reply.isNotEmpty) {
        entries.add(IntentHistoryTurn(role: 'assistant', text: reply));
      }
    }
    if (entries.length > intentHistoryMaxEntries) {
      entries.removeRange(0, entries.length - intentHistoryMaxEntries);
    }
    return entries;
  }

  /// The assistant's own words for a settled turn, so the model sees the
  /// question it asked or the result it gave. Turns with no assistant reply
  /// (queued, in flight, failed) contribute only the user's side.
  String? _assistantReply(ConversationTurn turn, SabStrings strings) =>
      switch (turn.phase) {
        HomePhase.discovery =>
          turn.candidates.map((service) => service.collectingBody).join(', '),
        HomePhase.clarifying => turn.intent?.clarifyingQuestion,
        HomePhase.conversational => strings.conversationalReply,
        HomePhase.notCovered => strings.notCoveredBody,
        _ => null,
      };

  Future<List<ServiceSummary>?> _settle(
    IntentResult intent, {
    required String request,
  }) async {
    // A non-command message is answered conversationally, never searched,
    // never recorded, and never counted as a clarification turn (FEAT-003,
    // user-flow Flow 2 Alternate Path K).
    if (intent.isNonCommand) {
      _updateCurrent(
        (turn) => turn.copyWith(
          phase: HomePhase.conversational,
          intent: intent,
          candidates: const [],
        ),
      );
      return null;
    }

    // A question from the model takes precedence over the catalogue search
    // fallback: when the request is too ambiguous to resolve, the honest next
    // step is the question even if the model offered no candidates
    // (FEAT-003/MQ-001, Flow 2 alternate path A). A resolution with no question
    // still falls through to search below.
    if (intent.needsClarification) {
      final asked = state.turns
          .where((turn) => turn.phase == HomePhase.clarifying)
          .length;
      if (asked >= homeClarificationLimit) {
        // Three questions in one conversation and still unresolved: search the
        // catalogue once, then state the gap with human support rather than
        // asking again or guessing (FEAT-003, MQ-001).
        return _searchFallback(request, intent: intent);
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
    if (intent.candidates.isEmpty) {
      // No question and no candidate: resolution found nothing, so search the
      // catalogue directly in case a plain service query still reaches
      // discovery (FEAT-004).
      return _searchFallback(request, intent: intent);
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
      (turn) => turn.copyWith(phase: HomePhase.notCovered, intent: intent),
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
      final intent = await _resolve(request);
      await _settle(intent, request: request);
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
