import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/payment/data/mock_payment_repository.dart';
import 'package:sabi_mobile/features/payment/data/payment_repository.dart';
import 'package:sabi_mobile/features/payment/data/providers.dart';
import 'package:sabi_mobile/features/payment/models/payment.dart';
import 'package:sabi_mobile/features/payment/payment_confirmation_screen.dart';
import 'package:sabi_mobile/features/payment/payment_strings.dart';
import 'package:sabi_mobile/models/account.dart';
import 'package:sabi_mobile/models/payment_case.dart';
import 'package:sabi_mobile/models/service_summary.dart';

import '../helpers.dart';

const _serviceId = 'svc_test';

PaymentObligation _obligation({
  PaymentKind kind = PaymentKind.standard,
  int? amount = 2500000,
}) => PaymentObligation(
  service: const ServiceSummary(
    serviceId: _serviceId,
    name: 'Land Use Charge',
    collectingBody: 'Lagos State Government',
    category: 'Government',
  ),
  amount: amount,
  kind: kind,
);

List<Override> _overrides({
  PaymentObligation? obligation,
  PaymentRepository? payments,
  FederalRepository? federal,
  BillRepository? bills,
  VerificationStatus kyc = VerificationStatus.verified,
  bool online = true,
}) => [
  paymentObligationProvider(_serviceId)
      .overrideWith((ref) => obligation ?? _obligation()),
  paymentRepositoryProvider.overrideWith(
    (ref) => payments ?? MockPaymentRepository(latency: Duration.zero),
  ),
  federalRepositoryProvider.overrideWith(
    (ref) => federal ?? MockFederalRepository(latency: Duration.zero),
  ),
  billRepositoryProvider.overrideWith(
    (ref) => bills ?? MockBillRepository(latency: Duration.zero),
  ),
  accountRepositoryProvider.overrideWith(
    (ref) => MockAccountRepository(latency: Duration.zero, kycStatus: kyc),
  ),
  if (!online) connectivityProvider.overrideWith(() => _OfflineConnectivity()),
];

/// A connectivity controller that starts offline.
class _OfflineConnectivity extends ConnectivityController {
  @override
  bool build() => false;
}

/// A cases repository whose refund always succeeds (FEAT-009, C-029).
class _RefundCases implements CasesRepository {
  @override
  Future<RefundResult> refund({
    required String paymentId,
    required String reason,
    required String idempotencyKey,
  }) async => RefundResult(
    paymentId: paymentId,
    status: 'reversed',
    refundReference: 'rfnd_$paymentId',
  );

  @override
  Future<CasePage> list({String? status, String? cursor, int limit = 20}) async =>
      const CasePage(cases: []);

  @override
  Future<CaseDetail> detail(String caseId) async => throw UnimplementedError();

  @override
  Future<CaseSummary> dispute({
    required String caseId,
    required String reason,
  }) async => throw UnimplementedError();
}

Future<void> _pump(
  WidgetTester tester, {
  List<Override> overrides = const [],
}) async {
  await pumpSab(
    tester,
    const PaymentConfirmationScreen(serviceId: _serviceId),
    overrides: overrides,
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the summary shows the amount, payee, and authorise action', (
    tester,
  ) async {
    await _pump(tester, overrides: _overrides());
    final payment = PaymentStrings.english;
    // The payee appears in the summary and the app bar.
    expect(find.text('Lagos State Government'), findsWidgets);
    expect(find.text(payment.authorisePayment), findsOneWidget);
    // ₦25,000.00 from 2,500,000 kobo.
    expect(find.textContaining('25,000.00'), findsOneWidget);
  });

  testWidgets('a settled payment shows the success notice', (tester) async {
    await _pump(tester, overrides: _overrides());
    final payment = PaymentStrings.english;
    await tester.tap(find.text(payment.authorisePayment));
    await tester.pumpAndSettle();
    expect(find.text(payment.successTitle), findsOneWidget);
    expect(find.text(payment.doneLabel), findsOneWidget);
  });

  testWidgets('a failed payment shows a reason and a retry', (tester) async {
    await _pump(
      tester,
      overrides: _overrides(
        payments: MockPaymentRepository(
          latency: Duration.zero,
          executeOutcome: ExecuteOutcome.failed,
        ),
      ),
    );
    final payment = PaymentStrings.english;
    await tester.tap(find.text(payment.authorisePayment));
    await tester.pumpAndSettle();
    expect(find.text(payment.failureTitle), findsOneWidget);
    expect(find.byType(SnackBar), findsNothing);
  });

  testWidgets('an unknown outcome shows the reconciling notice', (
    tester,
  ) async {
    await _pump(
      tester,
      overrides: _overrides(
        payments: MockPaymentRepository(
          latency: Duration.zero,
          executeOutcome: ExecuteOutcome.timeout,
        ),
      ),
    );
    final payment = PaymentStrings.english;
    await tester.tap(find.text(payment.authorisePayment));
    await tester.pumpAndSettle();
    expect(find.text(payment.reconcilingTitle), findsOneWidget);
  });

  testWidgets('an amount above the limit opens a second confirmation', (
    tester,
  ) async {
    await _pump(
      tester,
      overrides: _overrides(
        obligation: _obligation(
          amount: MockPaymentRepository.secondConfirmationLimit + 1,
        ),
      ),
    );
    final payment = PaymentStrings.english;
    await tester.tap(find.text(payment.authorisePayment));
    await tester.pumpAndSettle();
    expect(find.text(payment.secondConfirmationTitle), findsOneWidget);
    await tester.tap(find.text(payment.confirmAndPay));
    await tester.pumpAndSettle();
    expect(find.text(payment.successTitle), findsOneWidget);
  });

  testWidgets('a regulated payment on an unverified account is held for KYC', (
    tester,
  ) async {
    await _pump(
      tester,
      overrides: _overrides(
        obligation: _obligation(kind: PaymentKind.federal),
        kyc: VerificationStatus.unverified,
        federal: MockFederalRepository(
          latency: Duration.zero,
          requiresReference: true,
        ),
      ),
    );
    final payment = PaymentStrings.english;
    // The federal panel asks for the reference first.
    expect(find.text(payment.federalReferenceNeeded), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'TIN-123');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    await tester.tap(find.text(payment.authorisePayment));
    await tester.pumpAndSettle();
    expect(find.text(payment.heldForKycTitle), findsOneWidget);
    expect(find.text(payment.verifyNow), findsOneWidget);
  });

  testWidgets('a federal payment awaiting its official receipt says so', (
    tester,
  ) async {
    await _pump(
      tester,
      overrides: _overrides(
        obligation: _obligation(kind: PaymentKind.federal),
        federal: MockFederalRepository(
          latency: Duration.zero,
          requiresReference: true,
          receiptAwaiting: true,
        ),
      ),
    );
    final payment = PaymentStrings.english;
    await tester.enterText(find.byType(TextField), 'TIN-123');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    await tester.tap(find.text(payment.authorisePayment));
    await tester.pumpAndSettle();
    expect(find.text(payment.awaitingReceiptTitle), findsOneWidget);
  });

  testWidgets('a switched federal collection account offers a re-resolve', (
    tester,
  ) async {
    await _pump(
      tester,
      overrides: _overrides(
        obligation: _obligation(kind: PaymentKind.federal),
        federal: MockFederalRepository(
          latency: Duration.zero,
          collectionChanged: true,
        ),
      ),
    );
    final payment = PaymentStrings.english;
    // The conflict surfaces as a re-resolve notice with its action.
    expect(find.text(payment.collectionChangedTitle), findsOneWidget);
    expect(find.text(payment.reResolve), findsWidgets);
  });

  testWidgets('a bill asks for its recipient before authorising', (
    tester,
  ) async {
    await _pump(
      tester,
      overrides: _overrides(
        obligation: _obligation(kind: PaymentKind.bill, amount: null),
        bills: MockBillRepository(latency: Duration.zero, knownAmount: 200000),
      ),
    );
    final payment = PaymentStrings.english;
    expect(find.text(payment.billTitle), findsOneWidget);
    expect(find.text(payment.recipientLabel), findsOneWidget);
    await tester.enterText(find.byType(TextField), '07012345678');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    await tester.tap(find.text(payment.authorisePayment));
    await tester.pumpAndSettle();
    expect(find.text(payment.tokenLabel), findsOneWidget);
    expect(find.textContaining('TOKEN-'), findsOneWidget);
  });

  testWidgets('an offline biller prevents the payment before authorising', (
    tester,
  ) async {
    await _pump(
      tester,
      overrides: _overrides(
        obligation: _obligation(kind: PaymentKind.bill, amount: 200000),
        bills: MockBillRepository(
          latency: Duration.zero,
          billerOffline: true,
          knownAmount: 200000,
        ),
      ),
    );
    // A bill needs its recipient before the biller is reached; entering one
    // surfaces the offline biller as a prevented payment.
    await tester.enterText(find.byType(TextField), '07012345678');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(
      find.textContaining('This biller is offline right now'),
      findsOneWidget,
    );
  });

  testWidgets('offline shows the banner and blocks authorisation', (
    tester,
  ) async {
    await _pump(tester, overrides: _overrides(online: false));
    final payment = PaymentStrings.english;
    expect(find.text(payment.offlineNoAuthorisation), findsWidgets);
    // The primary action is disabled while offline.
    final button = tester.widget<ElevatedButton>(
      find.ancestor(
        of: find.text(payment.authorisePayment),
        matching: find.byType(ElevatedButton),
      ),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('a variable obligation offers to enter the amount', (
    tester,
  ) async {
    await _pump(
      tester,
      overrides: _overrides(obligation: _obligation(amount: null)),
    );
    final payment = PaymentStrings.english;
    expect(find.text(payment.changeAmount), findsOneWidget);
    await tester.tap(find.text(payment.changeAmount));
    await tester.pumpAndSettle();
    expect(find.text('Enter amount'), findsOneWidget);
  });

  testWidgets('a failed bill token shows the failure and the refund path', (
    tester,
  ) async {
    await _pump(
      tester,
      overrides: [
        ..._overrides(
          obligation: _obligation(kind: PaymentKind.bill, amount: 200000),
          bills: MockBillRepository(
            latency: Duration.zero,
            knownAmount: 200000,
            tokenFailed: true,
            tokenFailureReason: 'The meter was rejected.',
          ),
        ),
        casesRepositoryProvider.overrideWith((ref) => _RefundCases()),
      ],
    );
    final payment = PaymentStrings.english;
    await tester.enterText(find.byType(TextField), '07012345678');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    await tester.tap(find.text(payment.authorisePayment));
    await tester.pumpAndSettle();
    // The 409 is a failure, not an awaiting token, and the recovery is a
    // refund (C-035 revision 1; FEAT-009).
    expect(find.text(payment.billTokenFailedTitle), findsOneWidget);
    expect(find.text(payment.awaitingTokenTitle), findsNothing);
    expect(find.text(payment.startRefund), findsOneWidget);

    await tester.tap(find.text(payment.startRefund));
    await tester.pumpAndSettle();
    expect(find.text(payment.refundStartedTitle), findsOneWidget);
  });
}
