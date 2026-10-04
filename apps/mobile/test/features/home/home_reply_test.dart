import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/home/home_controller.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/intent_result.dart';
import 'package:sabi_mobile/models/service_summary.dart';

import '../../helpers.dart';

/// A catalogue double whose intent results are scripted per call, so the model
/// reply and the prewritten fallback can be told apart.
class _ScriptedCatalogue implements CatalogueRepository {
  _ScriptedCatalogue({required this.intents, this.searchResults = const []});

  final List<IntentResult> intents;
  final List<ServiceSummary> searchResults;
  int intentCalls = 0;

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  }) async {
    final index = intentCalls < intents.length
        ? intentCalls
        : intents.length - 1;
    intentCalls++;
    return intents[index];
  }

  @override
  Future<CatalogueSearchResult> search(String query) async =>
      CatalogueSearchResult(
        results: searchResults,
        noMatch: searchResults.isEmpty,
      );

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async =>
      throw const ServiceNotFoundException();
}

ServiceSummary _service(String id, String body) => ServiceSummary(
  serviceId: id,
  name: 'Land Use Charge',
  collectingBody: body,
  category: 'Government',
  confidence: 0.8,
);

final Finder _sendButton = find.ancestor(
  of: find.byTooltip('Send'),
  matching: find.byType(IconButton),
);

Future<void> _submit(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(_sendButton);
  await tester.pumpAndSettle();
}

void main() {
  final strings = SabStrings.english;

  testWidgets('a clarifying turn renders the model-authored reply', (
    tester,
  ) async {
    final catalogue = _ScriptedCatalogue(
      intents: const [
        IntentResult(
          intentType: 'unknown',
          confidence: 0.5,
          reply: 'Is it the council or the state you mean?',
        ),
      ],
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: [
        catalogueRepositoryProvider.overrideWith((ref) => catalogue),
        receiptRepositoryProvider.overrideWith(
          (ref) => MockReceiptRepository(receipts: const []),
        ),
      ],
    );
    await tester.pumpAndSettle();
    await _submit(tester, 'Hello');

    // The model's question is the assistant's message, not a localised string.
    expect(find.text('Is it the council or the state you mean?'), findsOneWidget);
  });

  testWidgets('a conversational turn renders the model-authored reply', (
    tester,
  ) async {
    final catalogue = _ScriptedCatalogue(
      intents: const [
        IntentResult(
          intentType: 'non_command',
          confidence: 0.2,
          reply: 'Hi Ngozi — what would you like to pay today?',
        ),
      ],
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: [
        catalogueRepositoryProvider.overrideWith((ref) => catalogue),
        receiptRepositoryProvider.overrideWith(
          (ref) => MockReceiptRepository(receipts: const []),
        ),
      ],
    );
    await tester.pumpAndSettle();
    await _submit(tester, 'Hello');

    expect(
      find.text('Hi Ngozi — what would you like to pay today?'),
      findsOneWidget,
    );
    // The prewritten greeting is the fallback, not the default.
    expect(find.text(strings.conversationalReply), findsNothing);
  });

  testWidgets('a conversational turn with no reply renders the fallback', (
    tester,
  ) async {
    final catalogue = _ScriptedCatalogue(
      intents: const [IntentResult(intentType: 'non_command', confidence: 0.2)],
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: [
        catalogueRepositoryProvider.overrideWith((ref) => catalogue),
        receiptRepositoryProvider.overrideWith(
          (ref) => MockReceiptRepository(receipts: const []),
        ),
      ],
    );
    await tester.pumpAndSettle();
    await _submit(tester, 'Hello');

    expect(find.text(strings.conversationalReply), findsOneWidget);
  });

  testWidgets('a no-resolution turn renders the model non-resolving reply', (
    tester,
  ) async {
    final catalogue = _ScriptedCatalogue(
      intents: const [
        IntentResult(
          intentType: 'unknown',
          confidence: 0.2,
          reply:
              'There is no resolution for that service right now. Name the collecting body and I will look again.',
        ),
      ],
      // No catalogue match, so the turn resolves to No resolution.
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: [
        catalogueRepositoryProvider.overrideWith((ref) => catalogue),
        receiptRepositoryProvider.overrideWith(
          (ref) => MockReceiptRepository(receipts: const []),
        ),
      ],
    );
    await tester.pumpAndSettle();
    await _submit(tester, 'pay my xyz subscription');

    expect(
      find.text(
        'There is no resolution for that service right now. Name the collecting body and I will look again.',
      ),
      findsOneWidget,
    );
    expect(find.text(strings.notCoveredBody), findsNothing);
  });

  testWidgets('a no-resolution turn with no reply renders the fallback', (
    tester,
  ) async {
    final catalogue = _ScriptedCatalogue(
      intents: const [IntentResult(intentType: 'unknown', confidence: 0.2)],
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: [
        catalogueRepositoryProvider.overrideWith((ref) => catalogue),
        receiptRepositoryProvider.overrideWith(
          (ref) => MockReceiptRepository(receipts: const []),
        ),
      ],
    );
    await tester.pumpAndSettle();
    await _submit(tester, 'pay my xyz subscription');

    // The No resolution state falls back to its own prewritten copy.
    expect(find.text(strings.notCoveredBody), findsOneWidget);
    expect(find.text(strings.unresolvedReply), findsNothing);
  });

  test(
    'a low-confidence turn with no reply degrades to search, not a blank turn',
    () async {
      final catalogue = _ScriptedCatalogue(
        intents: const [IntentResult(intentType: 'unknown', confidence: 0.2)],
        searchResults: [_service('svc_onitsha', 'Onitsha North LGA')],
      );
      final container = ProviderContainer(
        overrides: [
          catalogueRepositoryProvider.overrideWith((ref) => catalogue),
        ],
      );
      addTearDown(container.dispose);
      await container
          .read(homeControllerProvider.notifier)
          .submit('council levy');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.discovery);
      expect(state.fromSearch, isTrue);
    },
  );

  test('after the bound the unresolved fallback is used, not no-resolution', () {
    final turn = const ConversationTurn(
      request: 'one',
      phase: HomePhase.notCovered,
      afterClarificationBound: true,
    );
    expect(
      assistantReplyFor(turn, strings),
      strings.unresolvedReply,
    );
  });

  test('a plain catalogue miss uses the no-resolution fallback', () {
    final turn = const ConversationTurn(
      request: 'one',
      phase: HomePhase.notCovered,
    );
    expect(assistantReplyFor(turn, strings), strings.notCoveredBody);
  });

  test('a turn reply, when present, wins over the state fallback', () {
    final turn = const ConversationTurn(
      request: 'one',
      phase: HomePhase.notCovered,
      afterClarificationBound: true,
      intent: IntentResult(
        intentType: 'unknown',
        confidence: 0.3,
        reply: 'The model authored this after-bound reply.',
      ),
    );
    expect(
      assistantReplyFor(turn, strings),
      'The model authored this after-bound reply.',
    );
  });

  testWidgets('the newest reply is scrolled into view in a long conversation', (
    tester,
  ) async {
    final catalogue = _ScriptedCatalogue(
      intents: const [
        IntentResult(intentType: 'unknown', confidence: 0.5, reply: 'Q1?'),
        IntentResult(intentType: 'unknown', confidence: 0.5, reply: 'Q2?'),
        IntentResult(intentType: 'unknown', confidence: 0.5, reply: 'Q3?'),
        IntentResult(intentType: 'unknown', confidence: 0.2),
      ],
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: [
        catalogueRepositoryProvider.overrideWith((ref) => catalogue),
        receiptRepositoryProvider.overrideWith(
          (ref) => MockReceiptRepository(receipts: const []),
        ),
      ],
    );
    await tester.pumpAndSettle();
    final controller = containerOf(tester)
        .read(homeControllerProvider.notifier);
    for (final text in ['one', 'two', 'three', 'four']) {
      await controller.submit(text);
      await tester.pumpAndSettle();
    }
    // Five rendered items overflow the viewport; the assistant's last reply
    // must follow the exchange without a manual scroll.
    expect(find.text(strings.unresolvedReply), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
