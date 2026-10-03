/// Failures the live transport can raise, mapped from the shared error envelope
/// (`{ "error": { "code", "message", "details"? } }`; DELIVERY.md conventions).
///
/// Feature repositories translate these into the domain exceptions the screens
/// already understand, so a transport detail never reaches a screen. The one
/// exception is [ApiUnauthenticated], which callers map to the re-authorisation
/// flow rather than to a bare error.
library;

/// The API returned an error envelope, or a status the client did not expect.
class ApiException implements Exception {
  const ApiException({
    required this.statusCode,
    required this.code,
    required this.message,
    this.details,
  });

  /// HTTP status code.
  final int statusCode;

  /// Machine-readable code from the envelope, e.g. `invalid_request`.
  final String code;

  /// Plain-language message from the envelope.
  final String message;

  /// Optional structured details (already scrubbed server-side).
  final Object? details;

  @override
  String toString() => 'ApiException($statusCode, $code): $message';
}

/// A `401`: the session cookie is absent, expired, or rejected (C-002/C-004).
/// The caller shows the Re-authorisation sheet instead of a bare error, keeping
/// the current screen state (user-flow "Authentication Gate").
class ApiUnauthenticated extends ApiException {
  const ApiUnauthenticated({
    super.code = 'unauthenticated',
    super.message = 'Sign in to continue.',
    super.details,
  }) : super(statusCode: 401);
}

/// A `403`: authenticated but not permitted. Shown as a plain explanation
/// (user-flow "Error Recovery").
class ApiForbidden extends ApiException {
  const ApiForbidden({
    super.code = 'forbidden',
    super.message = 'You do not have access to this.',
    super.details,
  }) : super(statusCode: 403);
}

/// A `404`: the resource is unknown or not owned by the account.
class ApiNotFound extends ApiException {
  const ApiNotFound({
    super.code = 'not_found',
    super.message = 'We could not find that.',
    super.details,
  }) : super(statusCode: 404);
}

/// A `409`: the request conflicts with current state.
class ApiConflict extends ApiException {
  const ApiConflict({
    super.code = 'conflict',
    super.message = 'That conflicts with the current state.',
    super.details,
  }) : super(statusCode: 409);
}

/// The gateway could not be reached at all: no network, DNS failure, refused
/// connection, or a timeout. Callers surface this as the existing offline
/// states, never as an unhandled exception (user-flow "Error Recovery").
class ApiUnreachable implements Exception {
  const ApiUnreachable([this.cause]);

  /// The underlying transport error, kept for diagnostics only; never logged
  /// with request bodies or headers, which can carry the session cookie
  /// (NFR-024).
  final Object? cause;

  @override
  String toString() => 'ApiUnreachable';
}
