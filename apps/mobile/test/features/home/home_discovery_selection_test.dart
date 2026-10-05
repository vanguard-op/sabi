import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:sabi_mobile/a2ui/mock_surface_repository.dart';
import 'package:sabi_mobile/a2ui/providers.dart';
import 'package:sabi_mobile/a2ui/surface_repository.dart';
import 'package:sabi_mobile/a2ui/surface_task.dart';
import 'package:sabi_mobile/components/service_result_row.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/design_system/sab_art.dart';
import 'package:sabi_mobile/design_system/theme.dart';
import 'package:sabi_mobile/features/home/home_controller.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/intent_result.dart';
import 'package:sabi_mobile/models/service_summary.dart';

import '../../helpers.dart';

/// A catalogue whose intent results are scripted per call, so discovery and
/// clarification can both be reached deterministically.
class _Catalogue implements CatalogueRepository {
  _Catalogue(this.intents);

  final List<IntentResult> intents;
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
      const CatalogueSearchResult(results: [], noMatch: true);

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async =>
      throw const ServiceNotFoundException();
}

/// A surface repository that never composes, so the client's prewritten
/// discovery and confirmation fallbacks are exercised.
class _NoCompositionSurface implements SurfaceRepository {
  @override
  Future<Map<String, dynamic>> compose(SurfaceRequest request) async => {
    'messages': const <Map<String, dynamic>>[],
    'fallback': request.task.wire,
  };
}

ServiceSummary _service(String id, String body, {int? amount}) =>
    ServiceSummary(
      serviceId: id,
      name: 'Land Use Charge',
      collectingBody: body,
      category: 'Government',
      knownAmount: amount,
      confidence: 0.9,
    );

IntentResult _discovery(List<ServiceSummary> services, {int? amount}) =>
    IntentResult(
      intentType: 'bill_payment',
      target: services.first.collectingBody,
      amount: amount,
      reference: 'LUC-2026-0001',
      confidence: 0.9,
      candidates: services,
    );

IntentResult _clarifying(String question, List<ServiceSummary> candidates) =>
    IntentResult(
      intentType: 'unknown',
      confidence: 0.4,
      reply: question,
      candidates: candidates,
    );

ProviderContainer _container({
  required CatalogueRepository catalogue,
  SurfaceRepository? surface,
}) {
  final container = ProviderContainer(
    overrides: [
      catalogueRepositoryProvider.overrideWith((ref) => catalogue),
      surfaceRepositoryProvider.overrideWith(
        (ref) => surface ?? MockSurfaceRepository(latency: Duration.zero),
      ),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

final Finder _sendButton = find.ancestor(
  of: find.byTooltip('Send'),
  matching: find.byType(IconButton),
);

List<Override> _widgetOverrides(
  CatalogueRepository catalogue, {
  SurfaceRepository? surface,
}) => [
  catalogueRepositoryProvider.overrideWith((ref) => catalogue),
  receiptRepositoryProvider.overrideWith(
    (ref) => MockReceiptRepository(receipts: const []),
  ),
  surfaceRepositoryProvider.overrideWith(
    (ref) => surface ?? MockSurfaceRepository(latency: Duration.zero),
  ),
];

Future<void> _submit(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(_sendButton);
  await tester.pumpAndSettle();
}

void main() {
  group('selecting a discovery result confirms inline', () {
    test(
      'the composed picker selection moves the turn to confirmation',
      () async {
        final catalogue = _Catalogue([
          _discovery([
            _service('svc_north', 'Onitsha North LGA', amount: 250000),
            _service('svc_south', 'Onitsha South LGA'),
          ]),
        ]);
        final container = _container(catalogue: catalogue);
        final controller = container.read(homeControllerProvider.notifier);
        await controller.submit('council levy');
        expect(
          container.read(homeControllerProvider).phase,
          HomePhase.discovery,
        );

        await controller.selectService('svc_north');

        final state = container.read(homeControllerProvider);
        expect(state.phase, HomePhase.confirmation);
        expect(state.selectedService?.serviceId, 'svc_north');
        expect(state.turns.single.surfaceTask, SurfaceTask.confirmation);
        expect(state.turns.single.surface, isNotNull);
      },
    );

    test('a selection outside the resolved candidates is ignored', () async {
      final catalogue = _Catalogue([
        _discovery([_service('svc_north', 'Onitsha North LGA')]),
      ]);
      final container = _container(catalogue: catalogue);
      final controller = container.read(homeControllerProvider.notifier);
      await controller.submit('council levy');

      // The agent may only name a service the client resolved; an unknown id
      // changes nothing.
      await controller.selectService('svc_invented');

      expect(container.read(homeControllerProvider).phase, HomePhase.discovery);
      expect(container.read(homeControllerProvider).selectedService, isNull);
    });

    test(
      'a refused composition still confirms inline with the fallback',
      () async {
        final catalogue = _Catalogue([
          _discovery([
            _service('svc_north', 'Onitsha North LGA', amount: 250000),
          ]),
        ]);
        final container = _container(
          catalogue: catalogue,
          surface: _NoCompositionSurface(),
        );
        final controller = container.read(homeControllerProvider.notifier);
        await controller.submit('council levy');
        expect(container.read(homeControllerProvider).surface, isNull);

        await controller.selectService('svc_north');

        final state = container.read(homeControllerProvider);
        expect(state.phase, HomePhase.confirmation);
        expect(state.selectedService?.serviceId, 'svc_north');
        expect(state.turns.single.surfaceFailed, isTrue);
      },
    );

    testWidgets('tapping a composed result stays on Home and confirms inline', (
      tester,
    ) async {
      final catalogue = _Catalogue([
        _discovery([
          _service('svc_north', 'Onitsha North LGA', amount: 250000),
          _service('svc_south', 'Onitsha South LGA'),
        ]),
      ]);
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _widgetOverrides(catalogue),
      );
      await tester.pumpAndSettle();
      await _submit(tester, 'council levy');
      expect(find.byType(ServiceResultRow), findsNWidgets(2));

      await tester.tap(find.text('Onitsha North LGA'));
      await tester.pumpAndSettle();

      // No navigation: the confirmation is composed inline and the screen is
      // offered as the explicit alternate. The selected service's own payee and
      // known amount are shown, never a message or an invented value.
      expect(find.byType(HomeScreen), findsOneWidget);
      expect(find.byType(ServiceResultRow), findsNothing);
      expect(find.text('Onitsha North LGA'), findsOneWidget);
      expect(find.textContaining('2,500'), findsOneWidget);
      expect(find.text(SabStrings.english.openPaymentScreen), findsOneWidget);
      final state = containerOf(tester).read(homeControllerProvider);
      expect(state.phase, HomePhase.confirmation);
      expect(state.selectedService?.serviceId, 'svc_north');
    });

    testWidgets('a fallback discovery selection confirms inline too', (
      tester,
    ) async {
      final catalogue = _Catalogue([
        _discovery([
          _service('svc_north', 'Onitsha North LGA', amount: 250000),
        ]),
      ]);
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _widgetOverrides(
          catalogue,
          surface: _NoCompositionSurface(),
        ),
      );
      await tester.pumpAndSettle();
      await _submit(tester, 'council levy');
      expect(find.byType(ServiceResultRow), findsOneWidget);

      await tester.tap(find.text('Onitsha North LGA'));
      await tester.pumpAndSettle();

      // The prewritten confirmation fallback carries the selected service's own
      // known amount, not a zero, and keeps the screen as the alternate.
      expect(find.byType(HomeScreen), findsOneWidget);
      expect(find.text('Onitsha North LGA'), findsOneWidget);
      expect(find.textContaining('2,500'), findsOneWidget);
      expect(find.text(SabStrings.english.openPaymentScreen), findsOneWidget);
      expect(
        containerOf(tester).read(homeControllerProvider).phase,
        HomePhase.confirmation,
      );
    });

    testWidgets(
      'selecting a closest match in a clarification confirms inline',
      (tester) async {
        final catalogue = _Catalogue([
          _clarifying('Which one do you mean?', [
            _service('svc_north', 'Onitsha North LGA', amount: 250000),
          ]),
        ]);
        await pumpSab(
          tester,
          const HomeScreen(),
          overrides: _widgetOverrides(catalogue),
        );
        await tester.pumpAndSettle();
        await _submit(tester, 'council levy');
        expect(find.text('Just to confirm'), findsOneWidget);

        await tester.tap(find.text('Onitsha North LGA'));
        await tester.pumpAndSettle();

        expect(find.byType(HomeScreen), findsOneWidget);
        expect(
          containerOf(tester).read(homeControllerProvider).phase,
          HomePhase.confirmation,
        );
        expect(find.text(SabStrings.english.openPaymentScreen), findsOneWidget);
      },
    );
  });

  group('the payment screen is the explicit alternate', () {
    testWidgets('the confirmation action pushes the payment route', (
      tester,
    ) async {
      final catalogue = _Catalogue([
        _discovery([
          _service('svc_north', 'Onitsha North LGA', amount: 250000),
        ]),
      ]);
      await _pumpRoutedHome(tester, overrides: _widgetOverrides(catalogue));
      await tester.pumpAndSettle();
      await _submit(tester, 'council levy');

      await tester.tap(find.text('Onitsha North LGA'));
      await tester.pumpAndSettle();
      expect(find.byType(HomeScreen), findsOneWidget);

      await tester.tap(find.text(SabStrings.english.openPaymentScreen));
      await tester.pumpAndSettle();

      // The alternate action pushes the Payment Confirmation route, and the
      // conversation was never the fallback that pushed it.
      expect(find.text('PAY svc_north'), findsOneWidget);
    });
  });
}

/// Pumps Home inside a router with a stub payment route, so the alternate
/// action's push can be asserted without the full app.
Future<void> _pumpRoutedHome(
  WidgetTester tester, {
  required List<Override> overrides,
}) async {
  await initializeDateFormatting('en_NG');
  final router = GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(path: '/home', builder: (context, state) => const HomeScreen()),
      GoRoute(
        path: '/pay/:serviceId',
        builder: (context, state) =>
            Scaffold(body: Text('PAY ${state.pathParameters['serviceId']}')),
      ),
    ],
  );
  await tester.pumpWidget(
    SabArtMode(
      staticOnly: true,
      child: ProviderScope(
        overrides: overrides,
        child: MaterialApp.router(
          theme: buildSabTheme(Brightness.light),
          routerConfig: router,
        ),
      ),
    ),
  );
}
