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

/// A catalogue double that records the `history` it is handed, so the
/// conversation carried to C-009 can be asserted directly.
class _HistoryCatalogue implements CatalogueRepository {
  _HistoryCatalogue({this.intents = const [], this.searchResults = const []});

  final List<IntentResult> intents;
  final List<ServiceSummary> searchResults;
  final List<List<IntentHistoryTurn>> histories = [];
  int intentCalls = 0;
  int searchCalls = 0;

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  }) async {
    histories.add(List.of(history));
    final index = intentCalls < intents.length
        ? intentCalls
        : intents.length - 1;
    intentCalls++;
    return intents[index];
  }

  @override
  Future<CatalogueSearchResult> search(String query) async {
    searchCalls++;
    return CatalogueSearchResult(
      results: searchResults,
      noMatch: searchResults.isEmpty,
    );
  }

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

IntentResult _question(String question) => IntentResult(
  intentType: 'unknown',
  confidence: 0.5,
  reply: question,
);

IntentResult _discovery(String body) => IntentResult(
  intentType: 'bill_payment',
  confidence: 0.9,
  candidates: [_service('svc_$body', body)],
);

ProviderContainer _container(CatalogueRepository catalogue) {
  final container = ProviderContainer(
    overrides: [catalogueRepositoryProvider.overrideWith((ref) => catalogue)],
  );
  addTearDown(container.dispose);
  return container;
}

final Finder _sendButton = find.ancestor(
  of: find.byTooltip('Send'),
  matching: find.byType(IconButton),
);

void main() {
  test(
    'a non-command message is answered conversationally and not searched',
    () async {
      final catalogue = _HistoryCatalogue(
        intents: const [
          IntentResult(intentType: 'non_command', confidence: 0.2),
        ],
        searchResults: [_service('svc_x', 'Somewhere Council')],
      );
      final container = _container(catalogue);
      final controller = container.read(homeControllerProvider.notifier);
      await controller.submit('Hello');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.conversational);
      expect(state.turns, hasLength(1));
      expect(catalogue.searchCalls, 0);
      // The exchange is not rewritten as a coverage miss.
      expect(state.phase, isNot(HomePhase.notCovered));
    },
  );

  testWidgets('a greeting renders the conversational reply', (tester) async {
    final catalogue = _HistoryCatalogue(
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
    await tester.enterText(find.byType(TextField), 'Hello');
    await tester.pump();
    await tester.tap(_sendButton);
    await tester.pumpAndSettle();
    expect(find.text(SabStrings.english.conversationalReply), findsOneWidget);
    expect(find.text('No resolution yet'), findsNothing);
    expect(find.text('Just to confirm'), findsNothing);
  });

  test('the prior exchange is sent oldest first with both roles', () async {
    final catalogue = _HistoryCatalogue(
      intents: [_question('Which one?'), _question('Still which one?')],
    );
    final container = _container(catalogue);
    final controller = container.read(homeControllerProvider.notifier);
    await controller.submit('one');
    await controller.submit('two');
    // The first submission carries no history; the second carries the first.
    expect(catalogue.histories.first, isEmpty);
    final history = catalogue.histories[1];
    expect(history, hasLength(2));
    expect(history[0].role, 'user');
    expect(history[0].text, 'one');
    expect(history[1].role, 'assistant');
    expect(history[1].text, 'Which one?');
  });

  test(
    'history is trimmed to the most recent six entries, oldest first',
    () async {
      final catalogue = _HistoryCatalogue(
        intents: [_discovery('Lagos State Government')],
      );
      final container = _container(catalogue);
      final controller = container.read(homeControllerProvider.notifier);
      for (final request in ['one', 'two', 'three', 'four', 'five']) {
        await controller.submit(request);
      }
      final history = catalogue.histories.last;
      expect(history, hasLength(intentHistoryMaxEntries));
      expect(history.first.role, 'user');
      expect(history.first.text, 'two');
      expect(history.last.role, 'assistant');
      expect(history.last.text, 'Lagos State Government');
    },
  );

  test(
    'after three questions the request falls back to search, then the gap',
    () async {
      final catalogue = _HistoryCatalogue(
        intents: [
          _question('Q1'),
          _question('Q2'),
          _question('Q3'),
          _question('Q4'),
        ],
      );
      final container = _container(catalogue);
      final controller = container.read(homeControllerProvider.notifier);
      await controller.submit('one');
      expect(
        container.read(homeControllerProvider).phase,
        HomePhase.clarifying,
      );
      await controller.submit('two');
      expect(
        container.read(homeControllerProvider).phase,
        HomePhase.clarifying,
      );
      await controller.submit('three');
      expect(
        container.read(homeControllerProvider).phase,
        HomePhase.clarifying,
      );
      // The fourth low-confidence result is past the bound: the catalogue is
      // searched and, with no match, the gap is stated with support offered.
      await controller.submit('four');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.notCovered);
      expect(catalogue.searchCalls, 1);
      expect(state.turns, hasLength(4));
    },
  );

  test(
    'the third question can still resolve without reaching the gap',
    () async {
      final catalogue = _HistoryCatalogue(
        intents: [
          _question('Q1'),
          _question('Q2'),
          _discovery('Lagos State Government'),
        ],
      );
      final container = _container(catalogue);
      final controller = container.read(homeControllerProvider.notifier);
      await controller.submit('one');
      await controller.submit('two');
      await controller.submit('three');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.discovery);
      expect(catalogue.searchCalls, 0);
    },
  );

  test('a non-command answer does not consume a clarification turn', () async {
    final catalogue = _HistoryCatalogue(
      intents: [
        _question('Q1'),
        const IntentResult(intentType: 'non_command', confidence: 0.2),
        _question('Q2'),
      ],
    );
    final container = _container(catalogue);
    final controller = container.read(homeControllerProvider.notifier);
    await controller.submit('one');
    await controller.submit('thanks');
    expect(
      container.read(homeControllerProvider).phase,
      HomePhase.conversational,
    );
    await controller.submit('two');
    final state = container.read(homeControllerProvider);
    // Only one question has been asked, so the third turn is still a question.
    expect(state.phase, HomePhase.clarifying);
    expect(state.intent?.reply, 'Q2');
  });

  test(
    'abandoning a clarification records nothing and starts no search',
    () async {
      final catalogue = _HistoryCatalogue(intents: [_question('Q1')]);
      final container = _container(catalogue);
      await container.read(homeControllerProvider.notifier).submit('one');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.clarifying);
      expect(state.turns, hasLength(1));
      expect(catalogue.searchCalls, 0);
    },
  );
}
