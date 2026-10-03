import '../../../core/api_client.dart';
import '../../../core/api_exception.dart';
import '../models/payment.dart';
import '../models/payment_errors.dart';
import 'payment_repository.dart';

/// Live payment authorisation and execution against the gateway (FEAT-005;
/// C-017–C-019).
///
/// The transport detail never reaches the controller: every response code the
/// contract names maps to the domain exception the confirmation surface already
/// renders. A duplicate authorisation carries the existing payment from the
/// gateway's `details`, so the screen resumes that payment instead of starting a
/// second one.
class HttpPaymentRepository implements PaymentRepository {
  HttpPaymentRepository(this._api);

  final SabApiClient _api;

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
    try {
      final body = await _api.post(
        '/payments/authorise',
        body: {
          'serviceId': serviceId,
          'amount': amount,
          'currency': currency,
          'payeeReference': payeeReference,
          'paymentMethodId': paymentMethodId,
          'channel': channel,
          'secondConfirmation': secondConfirmation,
        },
        headers: _idempotency(idempotencyKey),
      );
      return AuthoriseResult.fromJson(body);
    } on ApiException catch (e) {
      throw _authorisationFailure(e);
    } on ApiUnreachable {
      rethrow;
    }
  }

  @override
  Future<ExecuteResult> execute({
    required String paymentId,
    required String mandateId,
    String? idempotencyKey,
  }) async {
    try {
      final body = await _api.post(
        '/payments/$paymentId/execute',
        body: {'mandateId': mandateId},
        headers: _idempotency(idempotencyKey),
      );
      return ExecuteResult.fromJson(body);
    } on ApiException catch (e) {
      throw _executionFailure(e);
    } on ApiUnreachable {
      rethrow;
    }
  }

  @override
  Future<List<PaymentSummary>> listPayments({
    String? cursor,
    int limit = 20,
    String? status,
  }) async {
    try {
      final body = await _api.get(
        '/payments',
        query: {
          'cursor': cursor,
          'limit': '$limit',
          'status': (status == null || status.isEmpty) ? null : status,
        },
      );
      return (body['payments'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => PaymentSummary.fromJson(e.cast<String, dynamic>()))
          .toList(growable: false);
    } on ApiException catch (e) {
      throw PaymentServerException(e.message);
    } on ApiUnreachable {
      rethrow;
    }
  }

  static Map<String, String>? _idempotency(String? key) {
    final trimmed = key?.trim();
    if (trimmed == null || trimmed.isEmpty) return null;
    return {'Idempotency-Key': trimmed};
  }

  /// C-017: an above-limit refusal is one distinguishable `422`, so the screen
  /// asks for the second confirmation rather than showing a generic failure.
  /// A duplicate `409` carries the existing payment in `details`.
  static PaymentException _authorisationFailure(ApiException e) {
    if (e.statusCode == 409) {
      final details = e.details is Map ? e.details as Map : const {};
      return DuplicateAuthorisationException(
        paymentId: (details['paymentId'] ?? '').toString(),
        railReference: details['railReference']?.toString(),
      );
    }
    return switch (e.statusCode) {
      402 => const InsufficientFundsException(),
      422 => const SecondConfirmationRequiredException(),
      _ => const InvalidAuthorisationException(),
    };
  }

  static PaymentException _executionFailure(ApiException e) =>
      switch (e.statusCode) {
        402 => const InsufficientFundsException(),
        409 => const MandateExpiredException(),
        410 => const MandateExpiredException(),
        422 => const MandateMismatchException(),
        404 => const PaymentServerException(),
        _ => PaymentServerException(e.message),
      };
}

/// Live federal government obligations (FEAT-006; C-030–C-032).
class HttpFederalRepository implements FederalRepository {
  HttpFederalRepository(this._api);

  final SabApiClient _api;

  @override
  Future<FederalPrepare> prepare({
    required String serviceId,
    String? payerReference,
  }) async {
    try {
      final body = await _api.post(
        '/payments/federal/prepare',
        body: {'serviceId': serviceId, 'payerReference': payerReference},
      );
      return FederalPrepare.fromJson(body);
    } on ApiException catch (e) {
      throw switch (e.statusCode) {
        409 => const CollectionAccountChangedException(),
        400 || 422 => const InvalidFederalServiceException(),
        _ => PaymentServerException(e.message),
      };
    } on ApiUnreachable {
      rethrow;
    }
  }

  @override
  Future<FederalReceipt> receipt(String paymentId) async {
    try {
      final response = await _api.getWithStatus(
        '/payments/federal/$paymentId/receipt',
      );
      // A `202` is the FTeR still being issued, a valid hold rather than a
      // failure (C-031). The controller keeps the payment open and retries.
      if (response.statusCode == 202) {
        return FederalReceipt(status: 'awaiting_receipt');
      }
      return FederalReceipt.fromJson(response.body);
    } on ApiException catch (e) {
      throw switch (e.statusCode) {
        409 => const FederalNotSettledException(),
        404 => const PaymentServerException(),
        _ => PaymentServerException(e.message),
      };
    } on ApiUnreachable {
      rethrow;
    }
  }

  @override
  Future<String> reconcile({
    required String paymentId,
    required String reason,
  }) async {
    try {
      final body = await _api.post(
        '/payments/federal/$paymentId/reconcile',
        body: {'reason': reason},
      );
      return (body['caseId'] ?? '').toString();
    } on ApiException catch (e) {
      throw PaymentServerException(e.message);
    } on ApiUnreachable {
      rethrow;
    }
  }
}

/// Live everyday bill payments (FEAT-007; C-033–C-035).
class HttpBillRepository implements BillRepository {
  HttpBillRepository(this._api);

  final SabApiClient _api;

  @override
  Future<BillValidation> validate({
    required String serviceId,
    required String recipientIdentifier,
    int? amount,
  }) async {
    try {
      final body = await _api.post(
        '/payments/bills/validate',
        body: {
          'serviceId': serviceId,
          'recipientIdentifier': recipientIdentifier,
          'amount': amount,
        },
      );
      return BillValidation.fromJson(body);
    } on ApiException catch (e) {
      throw _validationFailure(e);
    } on ApiUnreachable {
      rethrow;
    }
  }

  @override
  Future<BillPaymentResult> pay({
    required String serviceId,
    required String recipientIdentifier,
    required int amount,
    String currency = 'NGN',
    String? idempotencyKey,
  }) async {
    try {
      final body = await _api.post(
        '/payments/bills',
        body: {
          'serviceId': serviceId,
          'recipientIdentifier': recipientIdentifier,
          'amount': amount,
          'currency': currency,
        },
        headers: HttpPaymentRepository._idempotency(idempotencyKey),
      );
      return BillPaymentResult.fromJson(body);
    } on ApiException catch (e) {
      throw _paymentFailure(e);
    } on ApiUnreachable {
      rethrow;
    }
  }

  @override
  Future<BillToken> token(String paymentId) async {
    try {
      // A `202` carries `status: awaiting_token` and a retry interval, a `200`
      // carries the token; both parse into the same shape (C-035).
      final response = await _api.getWithStatus(
        '/payments/bills/$paymentId/token',
      );
      return BillToken.fromJson(response.body);
    } on ApiException catch (e) {
      throw switch (e.statusCode) {
        404 => const BillTokenNotFoundException(),
        _ => PaymentServerException(e.message),
      };
    } on ApiUnreachable {
      rethrow;
    }
  }

  /// C-033: a `503` is the biller offline and blocks payment before any debit.
  static PaymentException _validationFailure(ApiException e) =>
      switch (e.statusCode) {
        503 => const BillerOfflineException(),
        400 || 404 => const InvalidBillException(),
        _ => PaymentServerException(e.message),
      };

  /// C-034: a bill is authorised and executed in one call, so a funding refusal
  /// is a failed payment with no token.
  static PaymentException _paymentFailure(ApiException e) =>
      switch (e.statusCode) {
        503 => const BillerOfflineException(),
        402 => const BillInsufficientFundsException(),
        400 || 404 => const InvalidBillException(),
        _ => PaymentServerException(e.message),
      };
}
