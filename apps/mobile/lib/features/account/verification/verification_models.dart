import 'package:flutter/foundation.dart';

/// The account verification status (CONTRACTS.md C-022 `kycStatus`). Mirrors the
/// four states the screen documents: unverified, pending, verified, rejected.
enum KycStatus {
  unverified,
  pending,
  verified,
  rejected;

  static KycStatus parse(String raw) => switch (raw) {
    'pending' => KycStatus.pending,
    'verified' => KycStatus.verified,
    'rejected' => KycStatus.rejected,
    _ => KycStatus.unverified,
  };
}

/// The identity method a verification uses (C-020 `method`).
enum VerificationMethod {
  nin('nin'),
  bvn('bvn');

  const VerificationMethod(this.wire);

  final String wire;

  static VerificationMethod parse(String? raw) =>
      raw == 'bvn' ? VerificationMethod.bvn : VerificationMethod.nin;
}

/// The account-level verification view (CONTRACTS.md C-022).
///
/// [canCorrect] is the server's ruling on whether one more correction attempt
/// is allowed; the screen never loops a second failed correction back to the
/// form (FEAT-002 edge case, screens/05).
@immutable
class AccountVerification {
  const AccountVerification({
    required this.kycStatus,
    this.method,
    required this.canCorrect,
  });

  final KycStatus kycStatus;
  final VerificationMethod? method;
  final bool canCorrect;

  factory AccountVerification.fromJson(Map<String, dynamic> json) {
    final rawMethod = json['method']?.toString();
    return AccountVerification(
      kycStatus: KycStatus.parse((json['kycStatus'] ?? '').toString()),
      method: rawMethod == null || rawMethod.isEmpty
          ? null
          : VerificationMethod.parse(rawMethod),
      canCorrect: json['canCorrect'] == true,
    );
  }
}

/// The result of submitting an identity check (CONTRACTS.md C-020).
///
/// The wire `status` is `pending`, `verified`, `failed`, or `corrected`. The
/// screen treats `failed`/`corrected` as "no match" with a correction attempt,
/// and a `pending` submission is polled via [VerificationResult].
enum SubmissionStatus {
  pending,
  verified,
  failed,
  corrected;

  static SubmissionStatus parse(String raw) => switch (raw) {
    'verified' => SubmissionStatus.verified,
    'failed' => SubmissionStatus.failed,
    'corrected' => SubmissionStatus.corrected,
    _ => SubmissionStatus.pending,
  };
}

@immutable
class VerificationSubmission {
  const VerificationSubmission({
    required this.verificationId,
    required this.status,
  });

  final String verificationId;
  final SubmissionStatus status;

  factory VerificationSubmission.fromJson(Map<String, dynamic> json) =>
      VerificationSubmission(
        verificationId: json['verificationId'].toString(),
        status: SubmissionStatus.parse((json['status'] ?? '').toString()),
      );
}

/// A polled verification record (CONTRACTS.md C-021).
@immutable
class VerificationRecord {
  const VerificationRecord({
    required this.verificationId,
    required this.status,
    this.reason,
    this.verifiedAt,
  });

  final String verificationId;
  final KycStatus status;

  /// The provider's plain-language reason for a non-verified outcome.
  final String? reason;
  final DateTime? verifiedAt;

  bool get isTerminal =>
      status == KycStatus.verified || status == KycStatus.rejected;

  factory VerificationRecord.fromJson(Map<String, dynamic> json) {
    return VerificationRecord(
      verificationId: json['verificationId'].toString(),
      status: KycStatus.parse((json['status'] ?? '').toString()),
      reason: json['reason']?.toString(),
      verifiedAt: DateTime.tryParse(json['verifiedAt']?.toString() ?? ''),
    );
  }
}

/// Raised for a rejected identifier (C-020 400) so the screen can point at the
/// field rather than showing a generic failure.
class InvalidIdentifierException implements Exception {
  const InvalidIdentifierException();
}

/// Raised when a verification is already in progress (C-020 409).
class VerificationInProgressException implements Exception {
  const VerificationInProgressException();
}
