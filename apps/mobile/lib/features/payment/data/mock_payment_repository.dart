import '../../../models/service_summary.dart';
import '../models/payment.dart';
import '../models/payment_errors.dart';
import 'payment_repository.dart';

/// A payment sandbox for the Phase 2 build (D-027: payment features proceed
/// against mock and sandbox rails until the licensed partner is secured).
///
/// The mock is deterministic so every state the confirmation surface renders
/// can be exercised without a rail: it keys off the service id and the amount,
/// and exposes named knobs for the failure and edge branches. It is never a
/// source of truth — the live repository replaces it when the endpoints land.
class MockPaymentRepository implements PaymentRepository {
  MockPaymentRepository({
    this.latency = _defaultLatency,
    this.authoriseOutcome = AuthoriseOutcome.success,
    this.executeOutcome = ExecuteOutcome.success,
    Set<String> duplicateServices = const {},
  }) : _duplicateServices = {...duplicateServices};

  Duration latency;

  /// Force the authorise branch, independent of the amount.
  AuthoriseOutcome authoriseOutcome;

  /// Force the execute branch, independent of the authorise result.
  ExecuteOutcome executeOutcome;

  /// Service ids that simulate a duplicate authorisation carrying an existing
  /// payment id (C-017 409).
  final Set<String> _duplicateServices;

  int _sequence = 0;
  final Map<String, AuthoriseResult> _existing = {};

  static const Duration _defaultLatency = Duration(milliseconds: 350);

  /// The amount above which a second confirmation is required (C-017 422). The
  /// real limit is on the account; the sandbox uses one fixed threshold.
  static const int secondConfirmationLimit = 5000000; // ₦50,000

  int get _next => ++_sequence;

  @override
  Future<AuthoriseResult> authorise({
    required String serviceId,
    required int amount,
    String currency = 'NGN',
    String? payeeReference,
    String? paymentMethodId,
    String channel = 'app',
    bool secondConfirmation = false,
    String? idempotencyKey,
  }) async {
    await Future<void>.delayed(latency);
    if (amount <= 0) {
      throw const InvalidAuthorisationException();
    }
    switch (authoriseOutcome) {
      case AuthoriseOutcome.invalid:
        throw const InvalidAuthorisationException();
      case AuthoriseOutcome.insufficientFunds:
        throw const InsufficientFundsException();
      case AuthoriseOutcome.duplicate:
        final existing = _existing.putIfAbsent(
          serviceId,
          () => AuthoriseResult(
            paymentId: 'pay_dup_${_next.toString().padLeft(3, '0')}',
            status: PaymentState.pending,
            mandateId: 'mnd_dup_${_next.toString().padLeft(3, '0')}',
            railReference: 'RAIL-DUP-0001',
          ),
        );
        throw DuplicateAuthorisationException(
          paymentId: existing.paymentId,
          railReference: existing.railReference,
        );
      case AuthoriseOutcome.success:
        break;
    }
    if (_duplicateServices.contains(serviceId)) {
      final existing = _existing.putIfAbsent(
        serviceId,
        () => AuthoriseResult(
          paymentId: 'pay_dup_${_next.toString().padLeft(3, '0')}',
          status: PaymentState.pending,
          mandateId: 'mnd_dup_${_next.toString().padLeft(3, '0')}',
          railReference: 'RAIL-DUP-0001',
        ),
      );
      throw DuplicateAuthorisationException(
        paymentId: existing.paymentId,
        railReference: existing.railReference,
      );
    }
    // An amount above the limit without a second confirmation is refused; with
    // the second confirmation it proceeds (C-017 422; FEAT-005).
    if (amount > secondConfirmationLimit && !secondConfirmation) {
      throw const SecondConfirmationRequiredException();
    }
    final id = 'pay_${_next.toString().padLeft(4, '0')}';
    final result = AuthoriseResult(
      paymentId: id,
      status: PaymentState.initiated,
      mandateId: 'mnd_${_next.toString().padLeft(4, '0')}',
    );
    _existing[serviceId] = result;
    return result;
  }

  @override
  Future<ExecuteResult> execute({
    required String paymentId,
    required String mandateId,
    String? idempotencyKey,
  }) async {
    await Future<void>.delayed(latency);
    if (mandateId.isEmpty) {
      throw const MandateExpiredException();
    }
    return switch (executeOutcome) {
      ExecuteOutcome.success => ExecuteResult(
        paymentId: paymentId,
        status: PaymentState.succeeded,
        railReference: 'RAIL-${paymentId.toUpperCase()}',
      ),
      ExecuteOutcome.failed => ExecuteResult(
        paymentId: paymentId,
        status: PaymentState.failed,
      ),
      ExecuteOutcome.timeout => throw const RailTimeoutException(),
      ExecuteOutcome.limitAfterSecond =>
        throw const InsufficientFundsException(),
      ExecuteOutcome.mandateExpired => throw const MandateExpiredException(),
      ExecuteOutcome.mandateMismatch => throw const MandateMismatchException(),
    };
  }

  @override
  Future<List<PaymentSummary>> listPayments({
    String? cursor,
    int limit = 20,
    String? status,
  }) async {
    await Future<void>.delayed(latency);
    return const <PaymentSummary>[];
  }

  /// Seeds a stable existing authorisation so a duplicate branch can be
  /// demonstrated without a prior call.
  void seedAuthorisation(String serviceId, AuthoriseResult result) {
    _existing[serviceId] = result;
  }
}

/// Authorise branches the surface must handle.
enum AuthoriseOutcome { success, invalid, insufficientFunds, duplicate }

/// Execute branches the surface must handle.
enum ExecuteOutcome {
  success,
  failed,
  timeout,
  limitAfterSecond,
  mandateExpired,
  mandateMismatch,
}

/// A federal sandbox (FEAT-006, C-030–C-032). Keyed by service id so a federal
/// service can simulate a required payer reference, a switched collection
/// account, and an FTeR that arrives late.
class MockFederalRepository implements FederalRepository {
  MockFederalRepository({
    this.latency = const Duration(milliseconds: 350),
    this.requiresReference = true,
    this.collectionChanged = false,
    this.receiptAwaiting = false,
    this.amount,
  });

  Duration latency;

  /// A required payer reference: without it the prepare explains how to obtain
  /// one rather than paying (FEAT-006, Flow 2 step 6).
  bool requiresReference;

  /// The agency has switched its collection account, so a prepare conflicts
  /// until re-resolved (FEAT-006, alternate G).
  bool collectionChanged;

  /// The FTeR has not arrived yet, so the receipt reads awaiting (C-031 202).
  bool receiptAwaiting;

  /// The known obligation amount in minor units, or null when variable.
  int? amount;

  int receiptPolls = 0;

  static const String referenceInstructions =
      'You need your Taxpayer Identification Number from the FIRS portal before you can pay. Get it at tax.gov.ng, then come back.';

  @override
  Future<FederalPrepare> prepare({
    required String serviceId,
    String? payerReference,
  }) async {
    await Future<void>.delayed(latency);
    if (collectionChanged) {
      throw const CollectionAccountChangedException();
    }
    return FederalPrepare(
      serviceId: serviceId,
      collectingBody: 'Federal Inland Revenue Service',
      amount: amount,
      requiresReference: requiresReference,
      instructions: requiresReference && (payerReference ?? '').trim().isEmpty
          ? referenceInstructions
          : 'Pay to the agency collection account through Sabi.',
    );
  }

  @override
  Future<FederalReceipt> receipt(String paymentId) async {
    await Future<void>.delayed(latency);
    receiptPolls++;
    if (receiptAwaiting) {
      return const FederalReceipt(
        status: 'awaiting_receipt',
        retryAfterSeconds: 30,
      );
    }
    return const FederalReceipt(
      receiptId: 'ftr_0001',
      receiptNumber: 'FTeR-2026-000123',
      verificationStatus: 'verified',
    );
  }

  @override
  Future<String> reconcile({
    required String paymentId,
    required String reason,
  }) async {
    await Future<void>.delayed(latency);
    return 'case_$paymentId';
  }
}

/// An everyday-bill sandbox (FEAT-007, C-033–C-035). Keyed by service id so a
/// prepaid meter can return a token and an offline biller can block payment.
class MockBillRepository implements BillRepository {
  MockBillRepository({
    this.latency = const Duration(milliseconds: 350),
    this.billerOffline = false,
    this.knownAmount,
    this.range,
    this.tokenAwaiting = false,
    this.tokenFailed = false,
    this.tokenFailureReason,
    this.amountValid = true,
  });

  Duration latency;

  /// The biller is offline: validation and payment are prevented (C-033 503).
  bool billerOffline;

  /// A known amount in minor units, or null when the bill is variable.
  int? knownAmount;

  /// The accepted amount band for a variable bill, in minor units.
  BillRange? range;

  /// The token has not returned yet, so payment holds open (C-035 202).
  bool tokenAwaiting;

  /// The payment failed after the debit, so the token endpoint rejects it
  /// (C-035 409). The surface must show a failure and the refund path, never an
  /// awaiting state.
  bool tokenFailed;

  /// The biller's plain reason for the failed token, when it gives one.
  String? tokenFailureReason;

  /// Whether a recipient resolves; false drives the wrong-identifier branch.
  bool amountValid;

  int tokenPolls = 0;
  int validateCalls = 0;

  @override
  Future<BillValidation> validate({
    required String serviceId,
    required String recipientIdentifier,
    int? amount,
  }) async {
    await Future<void>.delayed(latency);
    validateCalls++;
    if (billerOffline) {
      throw const BillerOfflineException();
    }
    if (recipientIdentifier.trim().isEmpty || !amountValid) {
      return BillValidation(
        valid: false,
        recipientIdentifier: recipientIdentifier.trim(),
        reason:
            'That meter or phone number was not found. Check it and try again.',
      );
    }
    return BillValidation(
      valid: true,
      recipientIdentifier: recipientIdentifier.trim(),
      knownAmount: knownAmount,
      range: range,
    );
  }

  @override
  Future<BillPaymentResult> pay({
    required String serviceId,
    required String recipientIdentifier,
    required int amount,
    String currency = 'NGN',
    String? idempotencyKey,
  }) async {
    await Future<void>.delayed(latency);
    if (billerOffline) {
      throw const BillerOfflineException();
    }
    if (amount <= 0) {
      throw const InvalidBillException();
    }
    return BillPaymentResult(
      paymentId: 'bill_0001',
      status: PaymentState.succeeded,
      // A prepaid bill returns a token; an airtime or postpaid bill does not.
      // A failed token has no token at all, so the client must fetch it and
      // meet the 409 rather than settle immediately.
      token: (tokenAwaiting || tokenFailed) ? null : 'TOKEN-1234-5678-9012',
      receiptId: 'rcp_bill_0001',
    );
  }

  @override
  Future<BillToken> token(String paymentId) async {
    await Future<void>.delayed(latency);
    tokenPolls++;
    if (tokenFailed) {
      throw BillTokenFailedException(
        tokenFailureReason ??
            'The biller did not complete this payment, so no token was issued. You can request a refund.',
      );
    }
    if (tokenAwaiting) {
      return const BillToken(status: 'awaiting_token', retryAfterSeconds: 3);
    }
    return const BillToken(
      token: 'TOKEN-1234-5678-9012',
      receiptId: 'rcp_bill_0001',
    );
  }
}

/// The accepted amount band for a variable bill, independent of the contract
/// model so the sandbox can be configured before parsing.
class PaymentAmountRange {
  const PaymentAmountRange({required this.minimum, required this.maximum});

  final int minimum;
  final int maximum;
}

/// A fixed catalogue of the sandbox obligations the payment surface can open.
///
/// Home passes a `serviceId` from discovery; this resolves it to the obligation
/// the confirmation renders, so a deep link or a test can open any branch. An
/// unknown id resolves to a generic standard obligation rather than failing, so
/// the screen is never dead-ended.
abstract final class PaymentSandboxCatalogue {
  static const _federal = {
    'svc_lagos_land_use',
    'svc_onitsha_council',
    'svc_firs_tax',
  };
  static const _bills = {
    'svc_ikeja_electric',
    'svc_ekedc',
    'svc_mtn_airtime',
    'svc_water_board',
  };

  static PaymentKind kindFor(String serviceId) {
    if (_federal.contains(serviceId) || serviceId.contains('federal')) {
      return PaymentKind.federal;
    }
    if (_bills.contains(serviceId) || serviceId.contains('bill')) {
      return PaymentKind.bill;
    }
    return PaymentKind.standard;
  }

  /// Resolves a service id to the obligation the screen shows. Kept beside the
  /// sandbox repositories so the client has one place to replace at wiring.
  static ServiceSummary serviceFor(String serviceId) {
    if (serviceId == 'svc_ikeja_electric') {
      return const ServiceSummary(
        serviceId: 'svc_ikeja_electric',
        name: 'Electricity token',
        collectingBody: 'Ikeja Electric',
        category: 'Biller',
      );
    }
    if (serviceId == 'svc_mtn_airtime') {
      return const ServiceSummary(
        serviceId: 'svc_mtn_airtime',
        name: 'Airtime top-up',
        collectingBody: 'MTN Nigeria',
        category: 'Biller',
        knownAmount: 200000,
      );
    }
    if (serviceId == 'svc_water_board') {
      return const ServiceSummary(
        serviceId: 'svc_water_board',
        name: 'Water bill',
        collectingBody: 'Lagos Water Corporation',
        category: 'Biller',
      );
    }
    if (serviceId == 'svc_firs_tax') {
      return const ServiceSummary(
        serviceId: 'svc_firs_tax',
        name: 'Company income tax',
        collectingBody: 'Federal Inland Revenue Service',
        category: 'Government',
        knownAmount: 12500000,
      );
    }
    if (serviceId == 'svc_onitsha_council') {
      return const ServiceSummary(
        serviceId: 'svc_onitsha_council',
        name: 'Council levy',
        collectingBody: 'Onitsha North LGA',
        category: 'Government',
        knownAmount: 500000,
      );
    }
    // The Lagos land use charge the Home mock resolves (C-009).
    return const ServiceSummary(
      serviceId: 'svc_lagos_land_use',
      name: 'Land Use Charge',
      collectingBody: 'Lagos State Government',
      category: 'Government',
      knownAmount: 2500000,
    );
  }
}
