import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/case/case_controller.dart';
import 'package:sabi_mobile/models/payment_case.dart';

CaseDetail _detail({
  String id = 'case_1',
  String paymentId = 'pay_1',
  CaseType type = CaseType.failedNoDelivery,
  CaseStatus status = CaseStatus.awaitingProvider,
  String paymentStatus = 'failed',
}) => CaseDetail(
  paymentCase: PaymentCase(
    id: id,
    paymentId: paymentId,
    type: type,
    status: status,
    assigneeRole: 'support_operations_agent',
    openedAt: DateTime.utc(2026, 9, 29, 11, 0),
    updatedAt: DateTime.utc(2026, 9, 30, 9, 0),
  ),
  payment: CasePayment(
    paymentId: paymentId,
    serviceId: 'svc_1',
    amount: 500000,
    currency: 'NGN',
    payee: 'Ikeja Electric',
    status: paymentStatus,
    channel: 'app',
    createdAt: DateTime.utc(2026, 9, 29, 11, 0),
    updatedAt: DateTime.utc(2026, 9, 30, 9, 0),
  ),
  timeline: const [],
);

ProviderContainer _container(MockCasesRepository cases) {
  final container = ProviderContainer(
    overrides: [casesRepositoryProvider.overrideWith((ref) => cases)],
  );
  addTearDown(container.dispose);
  return container;
}

Future<CaseController> _load(
  ProviderContainer container, {
  String caseId = 'case_1',
}) async {
  final controller = container.read(caseControllerProvider(caseId).notifier);
  // The controller loads from a microtask on build; drain the event queue so the
  // zero-latency repository call settles before asserting.
  await pumpEventQueue();
  return controller;
}

void main() {
  test('a load failure is an error that can be retried', () async {
    final cases = MockCasesRepository(latency: Duration.zero)
      ..failNextDetail = true;
    final container = _container(cases);
    await _load(container);
    expect(
      container.read(caseControllerProvider('case_1')).phase,
      CasePhase.error,
    );

    await container.read(caseControllerProvider('case_1').notifier).load();
    expect(
      container.read(caseControllerProvider('case_1')).phase,
      CasePhase.ready,
    );
  });

  test('a refund is refused offline and allowed again online', () async {
    final container = _container(MockCasesRepository(latency: Duration.zero));
    await _load(container);
    expect(container.read(caseControllerProvider('case_1')).canRefund, isTrue);

    container.read(connectivityProvider.notifier).setOnline(false);
    container.read(caseControllerProvider('case_1').notifier).setOnline(false);
    expect(container.read(caseControllerProvider('case_1')).canRefund, isFalse);
    expect(container.read(caseControllerProvider('case_1')).online, isFalse);

    container.read(connectivityProvider.notifier).setOnline(true);
    container.read(caseControllerProvider('case_1').notifier).setOnline(true);
    expect(container.read(caseControllerProvider('case_1')).canRefund, isTrue);
  });

  test('a refund reads as refund-started and reports it', () async {
    final container = _container(MockCasesRepository(latency: Duration.zero));
    final controller = await _load(container);
    await controller.refund();
    final state = container.read(caseControllerProvider('case_1'));
    expect(state.phase, CasePhase.refunded);
    expect(state.notice, CaseNotice.refundSubmitted);
    // The state the user reads agrees with the outcome, and a second refund is
    // not offered.
    expect(state.presentation, CasePresentation.refundInitiated);
    expect(state.canRefund, isFalse);
  });

  test('a duplicate refund is reported, not swallowed', () async {
    final cases = MockCasesRepository(latency: Duration.zero)
      ..failNextRefund = true;
    final container = _container(cases);
    final controller = await _load(container);
    await controller.refund();
    final state = container.read(caseControllerProvider('case_1'));
    expect(state.phase, CasePhase.refunded);
    expect(state.notice, CaseNotice.refundBlocked);
  });

  test('a dispute on an escalated case is raised and reported', () async {
    final container = _container(
      MockCasesRepository(
        latency: Duration.zero,
        cases: [_detail(id: 'case_4', status: CaseStatus.escalated)],
      ),
    );
    final controller = await _load(container, caseId: 'case_4');
    expect(container.read(caseControllerProvider('case_4')).canDispute, isTrue);
    await controller.dispute();
    final state = container.read(caseControllerProvider('case_4'));
    expect(state.phase, CasePhase.disputed);
    expect(state.notice, CaseNotice.disputeSubmitted);
    expect(state.canDispute, isFalse);
  });

  test('a duplicate dispute is reported, not swallowed', () async {
    final container = _container(
      MockCasesRepository(
        latency: Duration.zero,
        cases: [
          _detail(
            id: 'case_5',
            type: CaseType.disputed,
            status: CaseStatus.escalated,
          ),
        ],
      ),
    );
    final controller = await _load(container, caseId: 'case_5');
    await controller.dispute();
    final state = container.read(caseControllerProvider('case_5'));
    expect(state.phase, CasePhase.ready);
    expect(state.notice, CaseNotice.disputeBlocked);
  });

  test('a resolved case offers neither action', () async {
    final container = _container(
      MockCasesRepository(
        latency: Duration.zero,
        cases: [
          _detail(
            id: 'case_6',
            type: CaseType.refund,
            status: CaseStatus.resolved,
            paymentStatus: 'refunded',
          ),
        ],
      ),
    );
    await _load(container, caseId: 'case_6');
    final state = container.read(caseControllerProvider('case_6'));
    expect(state.presentation, CasePresentation.resolved);
    expect(state.canRefund, isFalse);
    expect(state.canDispute, isFalse);
  });
}
