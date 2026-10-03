import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/features/account/verification/verification_models.dart';

void main() {
  group('C-022 account verification', () {
    test('parses a verified status with no method and no correction', () {
      final v = AccountVerification.fromJson({
        'kycStatus': 'verified',
        'method': null,
        'canCorrect': false,
      });
      expect(v.kycStatus, KycStatus.verified);
      expect(v.method, isNull);
      expect(v.canCorrect, isFalse);
    });

    test('parses a rejected status and an unknown status as unverified', () {
      expect(
        AccountVerification.fromJson({
          'kycStatus': 'rejected',
          'canCorrect': false,
        }).kycStatus,
        KycStatus.rejected,
      );
      expect(
        AccountVerification.fromJson({'kycStatus': 'nonsense'}).kycStatus,
        KycStatus.unverified,
      );
    });

    test('maps the bvn method only when named', () {
      expect(
        AccountVerification.fromJson({
          'kycStatus': 'unverified',
          'method': 'bvn',
        }).method,
        VerificationMethod.bvn,
      );
      expect(
        AccountVerification.fromJson({'kycStatus': 'unverified', 'method': ''})
            .method,
        isNull,
      );
    });
  });

  group('C-020 submission', () {
    test('reads a verified submission', () {
      final s = VerificationSubmission.fromJson({
        'verificationId': 'ver_1',
        'status': 'verified',
      });
      expect(s.verificationId, 'ver_1');
      expect(s.status, SubmissionStatus.verified);
    });

    test('an unknown submission status reads as pending', () {
      expect(
        VerificationSubmission.fromJson({
          'verificationId': 'ver_2',
          'status': 'weird',
        }).status,
        SubmissionStatus.pending,
      );
    });
  });

  group('C-021 verification record', () {
    test('parses a terminal record with a reason and timestamp', () {
      final r = VerificationRecord.fromJson({
        'verificationId': 'ver_3',
        'status': 'rejected',
        'reason': 'No match',
        'verifiedAt': null,
      });
      expect(r.status, KycStatus.rejected);
      expect(r.reason, 'No match');
      expect(r.isTerminal, isTrue);
    });

    test('a verified record belongs to no correction attempt', () {
      final r = VerificationRecord.fromJson({
        'verificationId': 'ver_4',
        'status': 'verified',
        'verifiedAt': '2026-10-03T10:00:00Z',
      });
      expect(r.status, KycStatus.verified);
      expect(r.verifiedAt, DateTime.utc(2026, 10, 3, 10));
      expect(r.isTerminal, isTrue);
    });
  });
}
