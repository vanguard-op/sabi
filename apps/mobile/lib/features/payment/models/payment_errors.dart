/// Failures a payment call can return, mapped from the contract error envelope
/// (DELIVERY.md: `{ "error": { "code", "message", "details"? } }`).
///
/// Each carries a plain-language [message] the surface shows and the action
/// that resolves it, so a screen can state a reason and a next step rather than
/// a code. The mock and the future HTTP client both raise these, so the
/// controller never sees a transport detail.
sealed class PaymentException implements Exception {
  const PaymentException(this.message);

  /// Plain-language reason shown to the user.
  final String message;

  @override
  String toString() => message;
}

/// C-017 400/422: the authorisation is missing or malformed.
class InvalidAuthorisationException extends PaymentException {
  const InvalidAuthorisationException([
    super.message = 'That authorisation is not valid.',
  ]);
}

/// C-017 402: insufficient funds, or the amount is over the account limit.
class InsufficientFundsException extends PaymentException {
  const InsufficientFundsException([
    super.message = 'There is not enough to cover this payment.',
  ]);
}

/// C-017 422: an amount above the user's limit requires a second confirmation.
/// The surface re-presents the total and asks the user to confirm again.
class SecondConfirmationRequiredException extends PaymentException {
  const SecondConfirmationRequiredException([
    super.message =
        'This amount is above your limit. Confirm once more to continue.',
  ]);
}

/// C-017 409: a duplicate authorisation. Carries the existing payment so the
/// client resumes that payment instead of creating a second one.
class DuplicateAuthorisationException extends PaymentException {
  const DuplicateAuthorisationException({
    required this.paymentId,
    this.railReference,
    String message = 'This payment was already started. Resuming it.',
  }) : super(message);

  final String paymentId;
  final String? railReference;
}

/// C-018 409/410: the mandate was already consumed or has expired. A fresh
/// authorisation is needed.
class MandateExpiredException extends PaymentException {
  const MandateExpiredException([
    super.message = 'Authorisation expired. Start the payment again.',
  ]);
}

/// C-018 422: the mandate does not bind the amount and payee being executed.
class MandateMismatchException extends PaymentException {
  const MandateMismatchException([
    super.message = 'The amount or payee changed. Start the payment again.',
  ]);
}

/// C-030 400: the service is not a valid federal collection.
class InvalidFederalServiceException extends PaymentException {
  const InvalidFederalServiceException([
    super.message = 'That is not a federal payment we can make.',
  ]);
}

/// C-030 409: the agency has switched its collection account. The obligation
/// must be re-resolved before payment (FEAT-006, alternate G).
class CollectionAccountChangedException extends PaymentException {
  const CollectionAccountChangedException([
    super.message = "The agency's collection account has changed. Re-resolve the obligation.",
  ]);
}

/// C-031 409: the payment did not succeed, so no official receipt exists.
class FederalNotSettledException extends PaymentException {
  const FederalNotSettledException([
    super.message =
        'The payment has not settled, so there is no official receipt yet.',
  ]);
}

/// C-033 503: the biller is offline; payment is prevented and no debit occurs.
class BillerOfflineException extends PaymentException {
  const BillerOfflineException([
    super.message = 'This biller is offline right now. Try again later.',
  ]);
}

/// C-033 400/404: the recipient is invalid or the service is unknown.
class InvalidBillException extends PaymentException {
  const InvalidBillException([
    super.message = 'That account could not be found.',
  ]);
}

/// C-034 402: insufficient funds for the bill.
class BillInsufficientFundsException extends PaymentException {
  const BillInsufficientFundsException([
    super.message = 'There is not enough to cover this bill.',
  ]);
}

/// C-035 404: the payment is unknown, so no token can be retrieved.
class BillTokenNotFoundException extends PaymentException {
  const BillTokenNotFoundException([
    super.message = 'We could not find that payment.',
  ]);
}

/// A rail call that timed out with an unknown outcome. The payment is pending
/// and must be reconciled, never retried blindly (FEAT-005, edge case).
class RailTimeoutException extends PaymentException {
  const RailTimeoutException([
    super.message = 'The rail did not confirm in time. The payment is pending and will be checked.',
  ]);
}

/// Any other server failure; the action can be retried.
class PaymentServerException extends PaymentException {
  const PaymentServerException([
    super.message = 'Something went wrong. Try again.',
  ]);
}
