import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/payment/data/mock_payment_repository.dart';
import 'package:sabi_mobile/features/payment/data/payment_repository.dart';
import 'package:sabi_mobile/features/payment/data/providers.dart';
import 'package:sabi_mobile/features/payment/models/payment.dart';
import 'package:sabi_mobile/features/payment/payment_controller.dart';
import 'package:sabi_mobile/models/account.dart';
import 'package:sabi_mobile/models/payment_case.dart';
import 'package:sabi_mobile/models/service_summary.dart';

/// The controller is the payment state machine; these tests drive it directly
/// so every branch a rail or the contract can return is exercised without a
/// widget, and the screen tests can focus on what the user sees.

ServiceSummary _service(String id) => ServiceSummary(
  serviceId: id,
  name: 'Land Use Charge',
  collectingBody: 'Lagos State Government',
  category: 'Government',
);

PaymentObligation _obligation({
  PaymentKind kind = PaymentKind.standard,
  int? amount = 2500000,
  String id = 'svc_test',
}) => PaymentObligation(service: _service(id), amount: amount, kind: kind);

ProviderContainer _container({
  PaymentRepository? payments,
  FederalRepository? federal,
  BillRepository? bills,
}) {
  final container = ProviderContainer(
    overrides: [
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
        (ref) => MockAccountRepository(latency: Duration.zero),
      ),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

/// A cases repository whose refund always succeeds, so the FEAT-009 refund path
/// can be exercised from the payment surface without a case seed.
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

void main() {
  test(
    'a standard obligation with a known amount is ready immediately',
    () async {
      final container = _container();
      final id = 'svc_test';
      final notifier = container.read(paymentControllerProvider(id).notifier);
      await notifier.resolve();
      expect(
        container.read(paymentControllerProvider(id)).phase,
        PaymentPhase.ready,
      );
    },
  );

  test('a variable obligation opens the amount entry state', () async {
    final id = 'svc_test';
    final obligation = _obligation(amount: null);
    final scoped = ProviderContainer(
      overrides: [
        paymentRepositoryProvider.overrideWith(
          (ref) => MockPaymentRepository(latency: Duration.zero),
        ),
        paymentObligationProvider(id).overrideWith((ref) => obligation),
      ],
    );
    addTearDown(scoped.dispose);
    final notifier = scoped.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    expect(
      scoped.read(paymentControllerProvider(id)).phase,
      PaymentPhase.amountEntry,
    );
  });

  test('a successful authorise and execute settles the payment', () async {
    final container = _container();
    final id = 'svc_test';
    final notifier = container.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    await notifier.submit();
    final state = container.read(paymentControllerProvider(id));
    expect(state.phase, PaymentPhase.settled);
    expect(state.paymentId, isNotNull);
  });

  test('an amount above the limit asks for a second confirmation', () async {
    final container = _container();
    final id = 'svc_test';
    final notifier = container.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    await notifier.setAmount(MockPaymentRepository.secondConfirmationLimit + 1);
    await notifier.submit();
    expect(
      container.read(paymentControllerProvider(id)).phase,
      PaymentPhase.secondConfirmation,
    );

    await notifier.confirmSecondTime();
    expect(
      container.read(paymentControllerProvider(id)).phase,
      PaymentPhase.settled,
    );
  });

  test('declining the second confirmation returns to the summary', () async {
    final container = _container();
    final id = 'svc_test';
    final notifier = container.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    await notifier.setAmount(MockPaymentRepository.secondConfirmationLimit + 1);
    await notifier.submit();
    notifier.declineSecondTime();
    expect(
      container.read(paymentControllerProvider(id)).phase,
      PaymentPhase.ready,
    );
  });

  test('a rail failure reports a reason and no settlement', () async {
    final container = _container(
      payments: MockPaymentRepository(
        latency: Duration.zero,
        executeOutcome: ExecuteOutcome.failed,
      ),
    );
    final id = 'svc_test';
    final notifier = container.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    await notifier.submit();
    final state = container.read(paymentControllerProvider(id));
    expect(state.phase, PaymentPhase.failure);
    expect(state.failure, isNotNull);
  });

  test('a rail timeout is reconciling, never an immediate retry', () async {
    final container = _container(
      payments: MockPaymentRepository(
        latency: Duration.zero,
        executeOutcome: ExecuteOutcome.timeout,
      ),
    );
    final id = 'svc_test';
    final notifier = container.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    await notifier.submit();
    expect(
      container.read(paymentControllerProvider(id)).phase,
      PaymentPhase.reconciling,
    );
  });

  test('insufficient funds fails cleanly with a reason', () async {
    final container = _container(
      payments: MockPaymentRepository(
        latency: Duration.zero,
        authoriseOutcome: AuthoriseOutcome.insufficientFunds,
      ),
    );
    final id = 'svc_test';
    final notifier = container.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    await notifier.submit();
    final state = container.read(paymentControllerProvider(id));
    expect(state.phase, PaymentPhase.failure);
    expect(state.failure, contains('enough'));
  });

  test('a duplicate authorisation resumes the existing payment once', () async {
    final container = _container(
      payments: MockPaymentRepository(
        latency: Duration.zero,
        // The resolved obligation normalises an unknown id to the sandbox's
        // land-use service, so the duplicate key is that service id.
        duplicateServices: {'svc_lagos_land_use'},
      ),
    );
    final id = 'svc_test';
    final notifier = container.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    await notifier.submit();
    final state = container.read(paymentControllerProvider(id));
    // The resumption executes the existing payment under its own idempotency
    // key, so the outcome is a single settlement rather than a second charge.
    expect(state.phase, PaymentPhase.settled);
    expect(state.duplicatePaymentId, isNotNull);
  });

  test(
    'a regulated payment on an unverified account is held, not failed',
    () async {
      final id = 'svc_test';
      final obligation = _obligation(kind: PaymentKind.federal, id: id);
      final scoped = ProviderContainer(
        overrides: [
          paymentRepositoryProvider.overrideWith(
            (ref) => MockPaymentRepository(latency: Duration.zero),
          ),
          federalRepositoryProvider.overrideWith(
            (ref) => MockFederalRepository(latency: Duration.zero),
          ),
          accountRepositoryProvider.overrideWith(
            (ref) => MockAccountRepository(
              latency: Duration.zero,
              kycStatus: VerificationStatus.unverified,
            ),
          ),
          paymentObligationProvider(id).overrideWith((ref) => obligation),
        ],
      );
      addTearDown(scoped.dispose);
      final notifier = scoped.read(paymentControllerProvider(id).notifier);
      await notifier.resolve();
      await notifier.setReference('TIN-123');
      await notifier.submit();
      expect(
        scoped.read(paymentControllerProvider(id)).phase,
        PaymentPhase.heldForKyc,
      );
    },
  );

  test('a federal collection without a reference asks for one', () async {
    final id = 'svc_fed';
    final scoped = ProviderContainer(
      overrides: [
        paymentRepositoryProvider.overrideWith(
          (ref) => MockPaymentRepository(latency: Duration.zero),
        ),
        federalRepositoryProvider.overrideWith(
          (ref) => MockFederalRepository(latency: Duration.zero),
        ),
        paymentObligationProvider(id)
            .overrideWith((ref) => _obligation(kind: PaymentKind.federal, id: id)),
      ],
    );
    addTearDown(scoped.dispose);
    final notifier = scoped.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    expect(
      scoped.read(paymentControllerProvider(id)).phase,
      PaymentPhase.referenceRequired,
    );
    // Supplying the reference re-resolves into the ready state.
    await notifier.setReference('TIN-123');
    expect(
      scoped.read(paymentControllerProvider(id)).phase,
      PaymentPhase.ready,
    );
  });

  test('a switched federal collection account is a conflict', () async {
    final id = 'svc_fed';
    final scoped = ProviderContainer(
      overrides: [
        paymentRepositoryProvider.overrideWith(
          (ref) => MockPaymentRepository(latency: Duration.zero),
        ),
        federalRepositoryProvider.overrideWith(
          (ref) => MockFederalRepository(
            latency: Duration.zero,
            collectionChanged: true,
          ),
        ),
        paymentObligationProvider(id)
            .overrideWith((ref) => _obligation(kind: PaymentKind.federal, id: id)),
      ],
    );
    addTearDown(scoped.dispose);
    final notifier = scoped.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    final state = scoped.read(paymentControllerProvider(id));
    expect(state.phase, PaymentPhase.collectionChanged);
    expect(state.failure, contains('collection account'));
  });

  test('a settled federal payment awaits the FTeR then shows it', () async {
    final id = 'svc_fed';
    final federal = MockFederalRepository(latency: Duration.zero);
    final scoped = ProviderContainer(
      overrides: [
        paymentRepositoryProvider.overrideWith(
          (ref) => MockPaymentRepository(latency: Duration.zero),
        ),
        federalRepositoryProvider.overrideWith((ref) => federal),
        accountRepositoryProvider.overrideWith(
          (ref) => MockAccountRepository(
            latency: Duration.zero,
            kycStatus: VerificationStatus.verified,
          ),
        ),
        paymentObligationProvider(id)
            .overrideWith((ref) => _obligation(kind: PaymentKind.federal, id: id)),
      ],
    );
    addTearDown(scoped.dispose);
    final notifier = scoped.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    await notifier.setReference('TIN-123');
    await notifier.submit();
    expect(
      scoped.read(paymentControllerProvider(id)).phase,
      PaymentPhase.settled,
    );
    expect(
      scoped.read(paymentControllerProvider(id)).federalReceipt?.receiptId,
      isNotNull,
    );

    // A late FTeR: the receipt reads awaiting and keeps checking.
    federal.receiptAwaiting = true;
    await notifier.retryProof();
    expect(
      scoped.read(paymentControllerProvider(id)).phase,
      PaymentPhase.awaitingReceipt,
    );
  });

  test('an offline device blocks authorisation', () async {
    final container = _container();
    container.read(connectivityProvider.notifier).setOnline(false);
    final id = 'svc_test';
    final notifier = container.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    expect(
      container.read(paymentControllerProvider(id)).phase,
      PaymentPhase.offline,
    );
    await notifier.submit();
    expect(
      container.read(paymentControllerProvider(id)).phase,
      PaymentPhase.offline,
    );
  });

  test('a bill validates its recipient before becoming ready', () async {
    final id = 'svc_bill';
    final scoped = ProviderContainer(
      overrides: [
        paymentRepositoryProvider.overrideWith(
          (ref) => MockPaymentRepository(latency: Duration.zero),
        ),
        billRepositoryProvider.overrideWith(
          (ref) =>
              MockBillRepository(latency: Duration.zero, knownAmount: 200000),
        ),
        paymentObligationProvider(id).overrideWith(
          (ref) => _obligation(kind: PaymentKind.bill, amount: null, id: id),
        ),
      ],
    );
    addTearDown(scoped.dispose);
    final notifier = scoped.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    expect(
      scoped.read(paymentControllerProvider(id)).phase,
      PaymentPhase.recipientRequired,
    );
    await notifier.setRecipient('07012345678');
    final state = scoped.read(paymentControllerProvider(id));
    expect(state.phase, PaymentPhase.ready);
    expect(state.effectiveAmount, 200000);
  });

  test(
    'an offline biller prevents the payment before it is authorised',
    () async {
      final id = 'svc_bill';
      final scoped = ProviderContainer(
        overrides: [
          paymentRepositoryProvider.overrideWith(
            (ref) => MockPaymentRepository(latency: Duration.zero),
          ),
          billRepositoryProvider.overrideWith(
            (ref) => MockBillRepository(
              latency: Duration.zero,
              billerOffline: true,
              knownAmount: 200000,
            ),
          ),
          paymentObligationProvider(id).overrideWith(
            (ref) => _obligation(kind: PaymentKind.bill, amount: 200000, id: id),
          ),
        ],
      );
      addTearDown(scoped.dispose);
      final notifier = scoped.read(paymentControllerProvider(id).notifier);
      await notifier.resolve();
      await notifier.setRecipient('07012345678');
      final state = scoped.read(paymentControllerProvider(id));
      expect(state.phase, PaymentPhase.failure);
      expect(state.failure, contains('offline'));
    },
  );

  test('a prepaid bill returns its token and settles', () async {
    final id = 'svc_bill';
    final scoped = ProviderContainer(
      overrides: [
        paymentRepositoryProvider.overrideWith(
          (ref) => MockPaymentRepository(latency: Duration.zero),
        ),
        billRepositoryProvider.overrideWith(
          (ref) =>
              MockBillRepository(latency: Duration.zero, knownAmount: 200000),
        ),
        paymentObligationProvider(id).overrideWith(
          (ref) => _obligation(kind: PaymentKind.bill, amount: 200000, id: id),
        ),
      ],
    );
    addTearDown(scoped.dispose);
    final notifier = scoped.read(paymentControllerProvider(id).notifier);
    await notifier.resolve();
    await notifier.setRecipient('07012345678');
    await notifier.submit();
    final state = scoped.read(paymentControllerProvider(id));
    expect(state.phase, PaymentPhase.settled);
    expect(state.billToken?.token, isNotNull);
  });

  test(
    'a failed bill token is a failure with a refund path, never awaiting',
    () async {
      final id = 'svc_bill';
      final scoped = ProviderContainer(
        overrides: [
          paymentRepositoryProvider.overrideWith(
            (ref) => MockPaymentRepository(latency: Duration.zero),
          ),
          billRepositoryProvider.overrideWith(
            (ref) => MockBillRepository(
              latency: Duration.zero,
              knownAmount: 200000,
              tokenFailed: true,
              tokenFailureReason: 'The meter was rejected.',
            ),
          ),
          casesRepositoryProvider.overrideWith((ref) => _RefundCases()),
          paymentObligationProvider(id).overrideWith(
            (ref) => _obligation(kind: PaymentKind.bill, amount: 200000, id: id),
          ),
        ],
      );
      addTearDown(scoped.dispose);
      final notifier = scoped.read(paymentControllerProvider(id).notifier);
      await notifier.resolve();
      await notifier.setRecipient('07012345678');
      await notifier.submit();

      final failed = scoped.read(paymentControllerProvider(id));
      expect(failed.phase, PaymentPhase.failure);
      expect(failed.refundAvailable, isTrue);
      expect(failed.failure, contains('meter'));
      // The 409 is never an awaiting token.
      expect(failed.billToken, isNull);

      await notifier.requestRefund();
      final refunded = scoped.read(paymentControllerProvider(id));
      expect(refunded.phase, PaymentPhase.refundRequested);
      expect(refunded.refundReference, isNotNull);
    },
  );
}
