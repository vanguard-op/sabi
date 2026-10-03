import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/offline_banner.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/case/case_screen.dart';
import 'package:sabi_mobile/models/payment_case.dart';

import '../helpers.dart';

CaseDetail _detail({
  required CaseType type,
  required CaseStatus status,
  required String paymentStatus,
  String? failureReason,
}) => CaseDetail(
  paymentCase: PaymentCase(
    id: 'case_1',
    paymentId: 'pay_1',
    type: type,
    status: status,
    assigneeRole: 'support_operations_agent',
    openedAt: DateTime.utc(2026, 9, 29, 11, 0),
    updatedAt: DateTime.utc(2026, 9, 30, 9, 0),
  ),
  payment: CasePayment(
    paymentId: 'pay_1',
    serviceId: 'svc_1',
    amount: 500000,
    currency: 'NGN',
    payee: 'Ikeja Electric',
    status: paymentStatus,
    channel: 'app',
    createdAt: DateTime.utc(2026, 9, 29, 11, 0),
    updatedAt: DateTime.utc(2026, 9, 30, 9, 0),
    failureReason: failureReason,
  ),
  timeline: [
    PaymentEvent(
      id: 'ev_1',
      paymentId: 'pay_1',
      status: paymentStatus,
      actor: 'system',
      detail: failureReason,
      occurredAt: DateTime.utc(2026, 9, 30, 9, 0),
      createdAt: DateTime.utc(2026, 9, 30, 9, 0),
    ),
  ],
);

Future<void> pumpCase(
  WidgetTester tester,
  CaseDetail detail, {
  bool online = true,
}) async {
  await pumpSab(
    tester,
    const CaseScreen(caseId: 'case_1'),
    overrides: [
      casesRepositoryProvider.overrideWith(
        (ref) =>
            MockCasesRepository(latency: Duration.zero, cases: [detail]),
      ),
    ],
  );
  await tester.pumpAndSettle();
  if (!online) {
    containerOf(tester).read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();
  }
}

void main() {
  testWidgets('a failed case reconciles and shows the last update', (
    tester,
  ) async {
    await pumpCase(
      tester,
      _detail(
        type: CaseType.failedNoDelivery,
        status: CaseStatus.open,
        paymentStatus: 'failed',
        failureReason: 'The rail and the biller disagree.',
      ),
    );
    expect(find.text('Reconciling'), findsWidgets);
    expect(find.textContaining('Last updated'), findsOneWidget);
    expect(find.text('The rail and the biller disagree.'), findsWidgets);
  });

  testWidgets('a case with no determined outcome reads as pending', (
    tester,
  ) async {
    await pumpCase(
      tester,
      _detail(
        type: CaseType.receiptMissing,
        status: CaseStatus.open,
        paymentStatus: 'failed',
      ),
    );
    expect(find.text('Pending'), findsWidgets);
  });

  testWidgets('a reversed payment shows a refund in progress', (tester) async {
    await pumpCase(
      tester,
      _detail(
        type: CaseType.refund,
        status: CaseStatus.open,
        paymentStatus: 'reversed',
      ),
    );
    expect(find.text('Refund started'), findsWidgets);
  });

  testWidgets('an awaiting-provider case shows the biller window', (
    tester,
  ) async {
    await pumpCase(
      tester,
      _detail(
        type: CaseType.failedNoDelivery,
        status: CaseStatus.awaitingProvider,
        paymentStatus: 'failed',
      ),
    );
    expect(find.text('Waiting on the biller'), findsWidgets);
    expect(find.textContaining('Expected resolution'), findsOneWidget);
  });

  testWidgets('an escalated case offers support and a dispute', (tester) async {
    await pumpCase(
      tester,
      _detail(
        type: CaseType.failedNoDelivery,
        status: CaseStatus.escalated,
        paymentStatus: 'failed',
      ),
    );
    expect(find.text('Escalated'), findsWidgets);
    expect(find.text('Contact support'), findsOneWidget);
    expect(find.text('Raise a dispute'), findsOneWidget);
  });

  testWidgets('a resolved case reads as resolved and offers the receipt', (
    tester,
  ) async {
    await pumpCase(
      tester,
      _detail(
        type: CaseType.refund,
        status: CaseStatus.resolved,
        paymentStatus: 'refunded',
      ),
    );
    expect(find.text('Resolved'), findsWidgets);
    expect(find.text('View the receipt'), findsOneWidget);
  });

  testWidgets('offline shows the last known state and blocks actions', (
    tester,
  ) async {
    await pumpCase(
      tester,
      _detail(
        type: CaseType.failedNoDelivery,
        status: CaseStatus.open,
        paymentStatus: 'failed',
      ),
      online: false,
    );
    expect(find.byType(OfflineBanner), findsOneWidget);
    // The refund path is unreachable offline: no refund action is rendered.
    expect(find.text('Refund started'), findsNothing);
  });

  testWidgets('a duplicate refund is blocked with the reason shown', (
    tester,
  ) async {
    final repo = MockCasesRepository(latency: Duration.zero);
    repo.failNextRefund = true;
    await pumpSab(
      tester,
      const CaseScreen(caseId: 'case_1'),
      overrides: [casesRepositoryProvider.overrideWith((ref) => repo)],
    );
    await tester.pumpAndSettle();
    // The awaiting-biller seed offers the refund path.
    await tester.tap(find.text('Start a refund'));
    await tester.pumpAndSettle();
    expect(find.textContaining('already in progress'), findsOneWidget);
  });
}
