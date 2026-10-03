import 'verification_models.dart';
import 'verification_repository.dart';

/// A scripted identity provider for the build. The verification status is
/// mutable so every screen state — unverified, verified, no match, pending
/// provider, rejected — can be exercised without the live NIN/BVN path
/// (dependency D3 is not yet secured).
///
/// The mock also models the flow the screen must enforce: a failed match allows
/// one correction, then stops offering the form (FEAT-002, screens/05).
class MockVerificationRepository implements VerificationRepository {
  MockVerificationRepository({
    this.latency = const Duration(milliseconds: 350),
    KycStatus initialStatus = KycStatus.unverified,
    VerificationMethod? initialMethod,
    bool initialCanCorrect = false,
  }) : _status = initialStatus,
       _method = initialMethod,
       _canCorrect = initialCanCorrect;

  Duration latency;
  KycStatus _status;
  VerificationMethod? _method;
  bool _canCorrect;

  /// When false the provider call fails like an unavailable service; the screen
  /// queues the check and reports it pending (C-020 202 + C-021 pending).
  bool providerAvailable = true;

  /// Forces the next submission to report no match regardless of input, so the
  /// no-match and correction states are reachable in demos and tests.
  bool failNextMatch = false;

  /// Forces the next submission to be rejected (account-level rejection).
  bool rejectNext = false;

  @override
  Future<AccountVerification> status() async {
    await Future<void>.delayed(latency);
    return AccountVerification(
      kycStatus: _status,
      method: _method,
      canCorrect: _canCorrect,
    );
  }

  @override
  Future<VerificationSubmission> submit({
    required VerificationMethod method,
    required String identifier,
  }) async {
    await Future<void>.delayed(latency);
    final trimmed = identifier.trim();
    // NIN is 11 digits, BVN is 11 digits; anything else is a rejected
    // identifier at the contract boundary (C-020 400).
    if (trimmed.length != 11 || int.tryParse(trimmed) == null) {
      throw const InvalidIdentifierException();
    }
    if (_status == KycStatus.pending) {
      throw const VerificationInProgressException();
    }
    _method = method;

    if (!providerAvailable) {
      // Queued with the provider; the account stays pending.
      _status = KycStatus.pending;
      _canCorrect = false;
      return const VerificationSubmission(
        verificationId: 'ver_mock_pending',
        status: SubmissionStatus.pending,
      );
    }

    if (rejectNext) {
      rejectNext = false;
      _status = KycStatus.rejected;
      _canCorrect = false;
      return const VerificationSubmission(
        verificationId: 'ver_mock_rejected',
        status: SubmissionStatus.failed,
      );
    }

    if (failNextMatch) {
      failNextMatch = false;
      // A first failed match allows one correction; a second does not.
      _canCorrect = !_canCorrect;
      _status = KycStatus.unverified;
      return const VerificationSubmission(
        verificationId: 'ver_mock_correct',
        status: SubmissionStatus.corrected,
      );
    }

    _status = KycStatus.verified;
    _canCorrect = false;
    return const VerificationSubmission(
      verificationId: 'ver_mock_verified',
      status: SubmissionStatus.verified,
    );
  }

  @override
  Future<VerificationRecord> check(String verificationId) async {
    await Future<void>.delayed(latency);
    return VerificationRecord(
      verificationId: verificationId,
      status: _status,
      reason: _status == KycStatus.rejected
          ? 'The identity record did not match.'
          : null,
      verifiedAt: _status == KycStatus.verified
          ? DateTime.utc(2026, 10, 3)
          : null,
    );
  }
}
