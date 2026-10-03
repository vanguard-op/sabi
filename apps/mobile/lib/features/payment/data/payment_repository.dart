import '../models/payment.dart';

/// Payment authorisation and execution (FEAT-005, CONTRACTS.md C-017–C-019).
///
/// The screen never talks to a transport directly; the mock in
/// `mock_payment_repository.dart` satisfies this shape until the endpoints are
/// wired. Money movements carry an idempotency key, and a call bound to an
/// amount and payee signs a mandate that a separate execute call consumes.
abstract class PaymentRepository {
  /// Signs a mandate for a specific amount and payee (C-017). Throws a
  /// [SecondConfirmationRequiredException] when an amount above the user's set
  /// limit needs a second confirmation, and a [DuplicateAuthorisationException]
  /// carrying the existing payment when the call is a repeat.
  Future<AuthoriseResult> authorise({
    required String serviceId,
    required int amount,
    String currency,
    String? payeeReference,
    String? paymentMethodId,
    String channel,
    bool secondConfirmation,
    String? idempotencyKey,
  });

  /// Executes a signed mandate through the rail (C-018).
  Future<ExecuteResult> execute({
    required String paymentId,
    required String mandateId,
    String? idempotencyKey,
  });

  /// The account's payments, newest first (C-019).
  Future<List<PaymentSummary>> listPayments({
    String? cursor,
    int limit,
    String? status,
  });
}

/// Federal government obligations (FEAT-006, CONTRACTS.md C-030–C-032).
abstract class FederalRepository {
  /// Resolves a federal obligation before payment (C-030). Throws
  /// [CollectionAccountChangedException] when the agency has switched its
  /// collection account.
  Future<FederalPrepare> prepare({
    required String serviceId,
    String? payerReference,
  });

  /// Retrieves the official FTeR, or reports it awaiting (C-031). Throws
  /// [FederalNotSettledException] when the payment has not succeeded.
  Future<FederalReceipt> receipt(String paymentId);

  /// Opens a reconciliation against the agency record (C-032).
  Future<String> reconcile({required String paymentId, required String reason});
}

/// Everyday bill payments (FEAT-007, CONTRACTS.md C-033–C-035).
abstract class BillRepository {
  /// Validates a recipient and amount before paying (C-033). Throws
  /// [BillerOfflineException] when the biller is offline.
  Future<BillValidation> validate({
    required String serviceId,
    required String recipientIdentifier,
    int? amount,
  });

  /// Pays a bill in one authorise-and-execute step (C-034).
  Future<BillPaymentResult> pay({
    required String serviceId,
    required String recipientIdentifier,
    required int amount,
    String currency,
    String? idempotencyKey,
  });

  /// Retrieves a prepaid token, or reports it awaiting (C-035).
  Future<BillToken> token(String paymentId);
}
