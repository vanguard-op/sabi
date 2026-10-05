import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/a2ui/providers.dart';
import 'package:sabi_mobile/a2ui/sabi_catalog.dart';
import 'package:sabi_mobile/a2ui/surface_repository.dart';
import 'package:sabi_mobile/a2ui/surface_task.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/home/home_controller.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/features/payment/payment_strings.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/intent_result.dart';
import 'package:sabi_mobile/models/service_summary.dart';

import '../../helpers.dart';

/// A catalogue whose only intent is a confirmation task, so the surface path is
/// reached deterministically.
class _ConfirmationCatalogue implements CatalogueRepository {
  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  }) async => IntentResult(
    intentType: 'bill_payment',
    target: 'Lagos State Government',
    amount: 2500000,
    reference: 'LUC-2026-0001',
    confidence: 0.9,
    constraints: {'task': 'confirmation'},
    candidates: const [
      ServiceSummary(
        serviceId: 'svc_lagos',
        name: 'Land Use Charge',
        collectingBody: 'Lagos State Government',
        category: 'Government',
        knownAmount: 2500000,
        confidence: 0.9,
      ),
    ],
  );

  @override
  Future<CatalogueSearchResult> search(String query) async =>
      const CatalogueSearchResult(results: [], noMatch: true);

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async =>
      throw const ServiceNotFoundException();
}

/// A surface repository that answers with streams a broken or hostile agent
/// could send, so the client fallback is exercised rather than assumed.
class _ScriptedSurface implements SurfaceRepository {
  _ScriptedSurface(this._responder);

  final Future<Map<String, dynamic>> Function(SurfaceRequest request)
  _responder;

  @override
  Future<Map<String, dynamic>> compose(SurfaceRequest request) =>
      _responder(request);
}

Map<String, dynamic> _stream({
  required String component,
  required Map<String, Object?> props,
  String catalogId = SabiCatalog.catalogId,
}) => {
  'messages': [
    {
      'version': 'v0.9',
      'createSurface': {'surfaceId': 'confirmation_1', 'catalogId': catalogId},
    },
    {
      'version': 'v0.9',
      'updateComponents': {
        'surfaceId': 'confirmation_1',
        'components': [
          {'id': 'root', 'component': component, ...props},
        ],
      },
    },
  ],
  'task': 'confirmation',
  'fallback': 'confirmation',
};

Future<ProviderContainer> _submitConfirmation(
  WidgetTester tester, {
  required SurfaceRepository surface,
}) async {
  await pumpSab(
    tester,
    const HomeScreen(),
    overrides: [
      catalogueRepositoryProvider.overrideWith(
        (ref) => _ConfirmationCatalogue(),
      ),
      receiptRepositoryProvider.overrideWith(
        (ref) => MockReceiptRepository(receipts: const []),
      ),
      surfaceRepositoryProvider.overrideWith((ref) => surface),
    ],
  );
  await tester.pumpAndSettle();
  final container = containerOf(tester);
  await container
      .read(homeControllerProvider.notifier)
      .submit('pay land use');
  await tester.pumpAndSettle();
  return container;
}

void main() {
  group('the task stays completable when the SDK cannot render', () {
    testWidgets('a no-composition response falls back to the client form', (
      tester,
    ) async {
      final container = await _submitConfirmation(
        tester,
        surface: _ScriptedSurface(
          // C-012 200 with a fallback and no messages: no compatible catalog or
          // a composition failure. The client renders its prewritten form.
          (request) async => {
            'messages': const <Map<String, dynamic>>[],
            'fallback': request.task.wire,
          },
        ),
      );
      expect(
        container.read(homeControllerProvider).phase,
        HomePhase.confirmation,
      );
      // The prewritten confirmation fallback shows the payee and amount from the
      // machine-actionable intent, never the reply.
      expect(find.text('Lagos State Government'), findsOneWidget);
      expect(find.textContaining('25,000'), findsOneWidget);
    });

    testWidgets('an unknown component falls back and never renders it', (
      tester,
    ) async {
      final container = await _submitConfirmation(
        tester,
        surface: _ScriptedSurface(
          (request) async => _stream(
            component: 'MysteryWidget',
            props: const {'amount': 2500000, 'payee': 'Lagos State Government'},
          ),
        ),
      );
      expect(
        container.read(homeControllerProvider).phase,
        HomePhase.confirmation,
      );
      expect(find.text('Lagos State Government'), findsOneWidget);
    });

    testWidgets('a surface naming another catalog falls back', (tester) async {
      final container = await _submitConfirmation(
        tester,
        surface: _ScriptedSurface(
          (request) async => _stream(
            component: 'ConfirmationSummary',
            catalogId: 'https://other.example/catalog.json',
            props: const {'amount': 2500000, 'payee': 'Lagos State Government'},
          ),
        ),
      );
      expect(
        container.read(homeControllerProvider).phase,
        HomePhase.confirmation,
      );
      expect(find.text('Lagos State Government'), findsOneWidget);
    });

    testWidgets('a transport failure falls back and holds the task', (
      tester,
    ) async {
      final container = await _submitConfirmation(
        tester,
        surface: _ScriptedSurface(
          (request) async => throw const InvalidCredentialException(),
        ),
      );
      expect(
        container.read(homeControllerProvider).phase,
        HomePhase.confirmation,
      );
      expect(find.text('Lagos State Government'), findsOneWidget);
      // The fallback form still carries the task: the authorise action is
      // client chrome and stays reachable when composition fails.
      expect(
        find.text(PaymentStrings.english.authorisePayment),
        findsOneWidget,
      );
    });
  });

  testWidgets('a catalog-conforming surface renders through the SDK', (
    tester,
  ) async {
    final container = await _submitConfirmation(
      tester,
      surface: _ScriptedSurface(
        (request) async => _stream(
          component: 'ConfirmationSummary',
          props: const {
            'amount': 2500000,
            'currency': 'NGN',
            'payee': 'Lagos State Government',
            'reference': 'LUC-2026-0001',
          },
        ),
      ),
    );
    expect(container.read(homeControllerProvider).surface, isNotNull);
    expect(find.text('Lagos State Government'), findsOneWidget);
    expect(
      find.text(PaymentStrings.english.authorisePayment),
      findsOneWidget,
    );
  });
}
