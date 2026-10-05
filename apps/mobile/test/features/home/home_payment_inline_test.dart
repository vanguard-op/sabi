import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/a2ui/mock_surface_repository.dart';
import 'package:sabi_mobile/a2ui/providers.dart';
import 'package:sabi_mobile/a2ui/sabi_catalog.dart';
import 'package:sabi_mobile/a2ui/surface_repository.dart';
import 'package:sabi_mobile/a2ui/surface_task.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/home/home_controller.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/features/payment/payment_controller.dart';
import 'package:sabi_mobile/features/payment/payment_strings.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/intent_result.dart';
import 'package:sabi_mobile/models/service_summary.dart';

import '../../helpers.dart';

const _serviceId = 'svc_variable';

/// A catalogue whose intent is a payment task, so the inline payment path is
/// reached deterministically.
class _PaymentCatalogue implements CatalogueRepository {
  _PaymentCatalogue(this.intent);

  final IntentResult intent;

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  }) async => intent;

  @override
  Future<CatalogueSearchResult> search(String query) async =>
      const CatalogueSearchResult(results: [], noMatch: true);

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async =>
      throw const ServiceNotFoundException();
}

/// A surface repository that never composes, so the client's prewritten
/// fallback form for the same task is exercised.
class _NoCompositionSurface implements SurfaceRepository {
  @override
  Future<Map<String, dynamic>> compose(SurfaceRequest request) async => {
    'messages': const <Map<String, dynamic>>[],
    'fallback': request.task.wire,
  };
}

ServiceSummary _variableService() => const ServiceSummary(
  serviceId: _serviceId,
  name: 'Electricity token',
  collectingBody: 'Ikeja Electric',
  category: 'Biller',
);

IntentResult _amountEntryIntent() => IntentResult(
  intentType: 'bill_payment',
  target: 'Ikeja Electric',
  confidence: 0.9,
  constraints: {
    'task': 'amount_entry',
    // The biller's accepted band, grounded from C-033.
    'range': {'minimum': 10000, 'maximum': 500000},
  },
  candidates: [_variableService()],
);

IntentResult _confirmationIntent() => IntentResult(
  intentType: 'bill_payment',
  target: 'Ikeja Electric',
  amount: 250000,
  confidence: 0.9,
  constraints: {'task': 'confirmation'},
  candidates: [
    ServiceSummary(
      serviceId: _serviceId,
      name: 'Airtime top-up',
      collectingBody: 'MTN Nigeria',
      category: 'Biller',
      knownAmount: 250000,
    ),
  ],
);

List<Override> _overrides(
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

final Finder _sendButton = find.ancestor(
  of: find.byTooltip('Send'),
  matching: find.byType(IconButton),
);

Future<void> _submitRequest(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField).first, text);
  await tester.pump();
  await tester.tap(_sendButton);
  await tester.pumpAndSettle();
}

Finder _amountField() => find.descendant(
  of: find.byType(SabAmountEntryField),
  matching: find.byType(TextField),
);

void main() {
  testWidgets('an amount-entry request composes inline and completes there', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(_PaymentCatalogue(_amountEntryIntent())),
    );
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'buy electricity');

    // The variable amount composes its AmountEntry surface inline rather than
    // routing to a screen.
    expect(find.byType(SabAmountEntryField), findsOneWidget);
    expect(
      containerOf(tester).read(homeControllerProvider).surfaceTask,
      SurfaceTask.amountEntry,
    );

    // A value outside the biller's C-033 range is refused.
    await tester.enterText(_amountField(), '50');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(find.text(SabStrings.english.amountOutOfRange), findsOneWidget);

    // A value inside the range binds the amount and moves to the confirmation.
    await tester.enterText(_amountField(), '5000');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(find.byType(SabAmountEntryField), findsNothing);
    expect(
      find.text(PaymentStrings.english.authorisePayment),
      findsOneWidget,
    );
    expect(
      containerOf(tester).read(paymentControllerProvider(_serviceId)).amount,
      500000,
    );

    // Authorising is the explicit confirmation and settles inline.
    await tester.tap(find.text(PaymentStrings.english.authorisePayment));
    await tester.pumpAndSettle();
    expect(
      find.text(PaymentStrings.english.successTitle),
      findsOneWidget,
    );
  });

  testWidgets('the confirmation authorise action completes inline', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(_PaymentCatalogue(_confirmationIntent())),
    );
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'buy airtime');

    // The confirmation is inline with the authorise action as its gate.
    expect(
      find.text(PaymentStrings.english.authorisePayment),
      findsOneWidget,
    );
    expect(
      containerOf(tester).read(homeControllerProvider).surfaceTask,
      SurfaceTask.confirmation,
    );

    await tester.tap(find.text(PaymentStrings.english.authorisePayment));
    await tester.pumpAndSettle();

    // The mandate was signed and executed in the conversation: the controller
    // settles and the success state renders inline.
    expect(
      containerOf(tester).read(paymentControllerProvider(_serviceId)).phase,
      PaymentPhase.settled,
    );
    expect(
      find.text(PaymentStrings.english.successTitle),
      findsOneWidget,
    );
  });

  testWidgets('a failed composition still carries the amount-entry task', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(
        _PaymentCatalogue(_amountEntryIntent()),
        surface: _NoCompositionSurface(),
      ),
    );
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'buy electricity');

    // The prewritten fallback form for the same task keeps the amount entry
    // completable inline.
    expect(find.byType(SabAmountEntryField), findsOneWidget);
    expect(
      containerOf(tester).read(homeControllerProvider).surfaceTask,
      SurfaceTask.amountEntry,
    );
  });
}
