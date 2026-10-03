import 'verification_models.dart';

/// Identity verification (FEAT-002; CONTRACTS.md C-020–C-022).
///
/// Until the endpoints are wired into the client transport the mock in
/// `verification_mock.dart` satisfies this shape. The screen depends only on the
/// abstraction, never on the transport or the mock.
abstract class VerificationRepository {
  /// The current account verification status (C-022).
  Future<AccountVerification> status();

  /// Submits an identity check (C-020). Throws
  /// [InvalidIdentifierException] on a rejected identifier and
  /// [VerificationInProgressException] when a check is already running.
  Future<VerificationSubmission> submit({
    required VerificationMethod method,
    required String identifier,
  });

  /// Polls a submitted verification (C-021).
  Future<VerificationRecord> check(String verificationId);
}
