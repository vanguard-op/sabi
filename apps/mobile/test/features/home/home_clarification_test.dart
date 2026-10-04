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

/// A catalogue double whose intent results are scripted per call, so the
/// precedence between a clarifying question and the search fallback can be
/// observed directly.
class _ScriptedCatalogue implements CatalogueRepository {
  _ScriptedCatalogue({required this.intents, this.searchResults = const []});

  final List<IntentResult> intents;
  final List<ServiceSummary> searchResults;
  int intentCalls = 0;
  int searchCalls = 0;

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

ProviderContainer _container(CatalogueRepository catalogue) {
  final container = ProviderContainer(
    overrides: [catalogueRepositoryProvider.overrideWith((ref) => catalogue)],
  );
  addTearDown(container.dispose);
  return container;
}

/// The composer's send action (the tooltip sits above the [IconButton]).
final Finder _sendButton = find.ancestor(
  of: find.byTooltip('Send'),
  matching: find.byType(IconButton),
);

void main() {
  test(
    'a no-candidate clarification asks the question instead of searching',
    () async {
      final catalogue = _ScriptedCatalogue(
        intents: const [
          IntentResult(
            intentType: 'unknown',
            confidence: 0.5,
            clarifyingQuestion: 'What would you like to pay for?',
          ),
        ],
        searchResults: [_service('svc_x', 'Somewhere Council')],
      );
      final container = _container(catalogue);
      await container.read(homeControllerProvider.notifier).submit('Hello');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.clarifying);
      expect(
        state.intent?.clarifyingQuestion,
        'What would you like to pay for?',
      );
      expect(catalogue.searchCalls, 0);
    },
  );

  test('confidence in [0.6, 0.70) with a question still clarifies', () async {
    final catalogue = _ScriptedCatalogue(
      intents: const [
        IntentResult(
          intentType: 'unknown',
          confidence: 0.65,
          clarifyingQuestion: 'Which one do you mean?',
        ),
      ],
    );
    final container = _container(catalogue);
    await container.read(homeControllerProvider.notifier).submit('pay my bill');
    expect(container.read(homeControllerProvider).phase, HomePhase.clarifying);
  });

  test('a question with candidates is preferred over the fallback', () async {
    final catalogue = _ScriptedCatalogue(
      intents: [
        IntentResult(
          intentType: 'bill_payment',
          confidence: 0.3,
          clarifyingQuestion: 'Which electricity provider?',
          candidates: [_service('svc_ikeja', 'Ikeja Electric')],
        ),
      ],
      searchResults: [_service('svc_other', 'Other')],
    );
    final container = _container(catalogue);
    await container.read(homeControllerProvider.notifier).submit('electricity');
    final state = container.read(homeControllerProvider);
    expect(state.phase, HomePhase.clarifying);
    expect(catalogue.searchCalls, 0);
  });

  test('a resolution with no question still falls back to search', () async {
    final catalogue = _ScriptedCatalogue(
      intents: const [IntentResult(intentType: 'unknown', confidence: 0.2)],
      searchResults: [_service('svc_onitsha', 'Onitsha North LGA')],
    );
    final container = _container(catalogue);
    await container
        .read(homeControllerProvider.notifier)
        .submit('council levy');
    final state = container.read(homeControllerProvider);
    expect(catalogue.searchCalls, 1);
    expect(state.phase, HomePhase.discovery);
    expect(state.fromSearch, isTrue);
  });

  test('a search miss with no question stays not covered', () async {
    final catalogue = _ScriptedCatalogue(
      intents: const [IntentResult(intentType: 'unknown', confidence: 0.18)],
    );
    final container = _container(catalogue);
    await container.read(homeControllerProvider.notifier).submit('school fees');
    expect(container.read(homeControllerProvider).phase, HomePhase.notCovered);
  });

  test(
    'a second unresolved answer asks a second question, not the gap',
    () async {
      final catalogue = _ScriptedCatalogue(
        intents: const [
          IntentResult(
            intentType: 'unknown',
            confidence: 0.5,
            clarifyingQuestion: 'Which one?',
          ),
          IntentResult(
            intentType: 'unknown',
            confidence: 0.5,
            clarifyingQuestion: 'Still which one?',
          ),
        ],
      );
      final container = _container(catalogue);
      final controller = container.read(homeControllerProvider.notifier);
      await controller.submit('Hello');
      expect(
        container.read(homeControllerProvider).phase,
        HomePhase.clarifying,
      );
      // The conversation may ask up to three questions, so the second
      // low-confidence answer is narrowed into a second question rather than
      // abandoned to the not-covered state (FEAT-003).
      await controller.submit('not sure');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.clarifying);
      expect(state.intent?.clarifyingQuestion, 'Still which one?');
      expect(state.turns, hasLength(2));
    },
  );

  testWidgets('a no-candidate clarification renders the question', (
    tester,
  ) async {
    final catalogue = _ScriptedCatalogue(
      intents: const [
        IntentResult(
          intentType: 'unknown',
          confidence: 0.5,
          clarifyingQuestion: 'What would you like to pay for?',
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
    await tester.enterText(find.byType(TextField), 'Hello');
    await tester.pump();
    await tester.tap(_sendButton);
    await tester.pumpAndSettle();
    expect(find.text('Just to confirm'), findsOneWidget);
    expect(find.text('What would you like to pay for?'), findsOneWidget);
    expect(find.text('Not covered yet'), findsNothing);
  });

  testWidgets(
    'a no-candidate clarification hides the closest-matches caption',
    (tester) async {
      final catalogue = _ScriptedCatalogue(
        intents: const [
          IntentResult(
            intentType: 'unknown',
            confidence: 0.5,
            clarifyingQuestion: 'What would you like to pay for?',
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
      await tester.enterText(find.byType(TextField), 'Hello');
      await tester.pump();
      await tester.tap(_sendButton);
      await tester.pumpAndSettle();
      // The question is rendered, but with no candidates there is nothing to
      // label, so the caption must not appear as an empty heading.
      expect(find.text('What would you like to pay for?'), findsOneWidget);
      expect(find.text('CLOSEST MATCHES'), findsNothing);
    },
  );
}
