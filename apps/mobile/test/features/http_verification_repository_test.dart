import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sabi_mobile/core/api_client.dart';
import 'package:sabi_mobile/core/api_config.dart';
import 'package:sabi_mobile/core/api_exception.dart';
import 'package:sabi_mobile/features/account/verification/http_verification_repository.dart';
import 'package:sabi_mobile/features/account/verification/verification_models.dart';

const _config = ApiConfig(baseUrl: 'http://10.0.2.2:8000/v1');

/// Answers by request path and keeps the exact request the repository sent, so
/// the test can assert the C-020 body and that each contract path is dispatched.
class _RecordingClient extends http.BaseClient {
  _RecordingClient(this.responses);

  final Map<String, ({int status, Object body})> responses;
  final List<String> requestPaths = [];
  final List<String> requestBodies = [];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requestPaths.add(request.url.path);
    requestBodies.add(request is http.Request ? request.body : '');
    final response = responses[request.url.path];
    if (response == null) {
      throw StateError('No stub for ${request.url.path}');
    }
    return http.StreamedResponse(
      Stream.value(utf8.encode(jsonEncode(response.body))),
      response.status,
      headers: {'content-type': 'application/json'},
    );
  }
}

HttpVerificationRepository _repo(
  Map<String, ({int status, Object body})> responses,
) => HttpVerificationRepository(
  SabApiClient(config: _config, httpClient: _RecordingClient(responses)),
);

void main() {
  group('status (C-022)', () {
    test('a 200 maps the account verification view', () async {
      final repo = _repo({
        '/v1/account/verification': (
          status: 200,
          body: {'kycStatus': 'verified', 'method': 'nin', 'canCorrect': false},
        ),
      });
      final status = await repo.status();
      expect(status.kycStatus, KycStatus.verified);
      expect(status.method, VerificationMethod.nin);
      expect(status.canCorrect, isFalse);
    });

    test('a missing method and canCorrect parse to an unverified account', () async {
      final repo = _repo({
        '/v1/account/verification': (
          status: 200,
          body: {'kycStatus': 'unverified', 'method': null, 'canCorrect': true},
        ),
      });
      final status = await repo.status();
      expect(status.kycStatus, KycStatus.unverified);
      expect(status.method, isNull);
      expect(status.canCorrect, isTrue);
    });
  });

  group('submit (C-020)', () {
    test('a 202 posts the camelCase method and identifier and parses the id', () async {
      final client = _RecordingClient({
        '/v1/identity/verifications': (
          status: 202,
          body: {'verificationId': 'ver_1', 'status': 'pending'},
        ),
      });
      final repo = HttpVerificationRepository(
        SabApiClient(config: _config, httpClient: client),
      );
      final submission = await repo.submit(
        method: VerificationMethod.bvn,
        identifier: '12345678901',
      );
      expect(submission.verificationId, 'ver_1');
      expect(submission.status, SubmissionStatus.pending);
      expect(client.requestPaths, ['/v1/identity/verifications']);
      expect(
        jsonDecode(client.requestBodies.single),
        {'method': 'bvn', 'identifier': '12345678901'},
      );
    });

    test('a 400 is a rejected identifier, not a generic failure', () {
      final repo = _repo({
        '/v1/identity/verifications': (
          status: 400,
          body: {
            'error': {'code': 'invalid_identifier', 'message': 'Invalid NIN.'},
          },
        ),
      });
      expect(
        () => repo.submit(
          method: VerificationMethod.nin,
          identifier: 'bad',
        ),
        throwsA(isA<InvalidIdentifierException>()),
      );
    });

    test('a 409 is a check already in progress', () {
      final repo = _repo({
        '/v1/identity/verifications': (
          status: 409,
          body: {
            'error': {'code': 'conflict', 'message': 'Already running.'},
          },
        ),
      });
      expect(
        () => repo.submit(
          method: VerificationMethod.nin,
          identifier: '12345678901',
        ),
        throwsA(isA<VerificationInProgressException>()),
      );
    });
  });

  group('check (C-021)', () {
    test('a 200 maps the verification record', () async {
      final repo = _repo({
        '/v1/identity/verifications/ver_1': (
          status: 200,
          body: {
            'verificationId': 'ver_1',
            'method': 'nin',
            'status': 'verified',
            'reason': null,
            'verifiedAt': '2026-10-03T00:00:00Z',
          },
        ),
      });
      final record = await repo.check('ver_1');
      expect(record.verificationId, 'ver_1');
      expect(record.status, KycStatus.verified);
      expect(record.verifiedAt, DateTime.utc(2026, 10, 3));
      expect(record.isTerminal, isTrue);
    });

    test('a failed match keeps the provider reason', () async {
      final repo = _repo({
        '/v1/identity/verifications/ver_2': (
          status: 200,
          body: {
            'verificationId': 'ver_2',
            'method': 'nin',
            'status': 'failed',
            'reason': 'The identity record did not match.',
            'verifiedAt': null,
          },
        ),
      });
      final record = await repo.check('ver_2');
      expect(record.status, KycStatus.unverified);
      expect(record.reason, 'The identity record did not match.');
      expect(record.isTerminal, isFalse);
    });

    test('a 404 is a retryable server failure', () {
      final repo = _repo({
        '/v1/identity/verifications/missing': (
          status: 404,
          body: {
            'error': {'code': 'not_found', 'message': 'Unknown verification.'},
          },
        ),
      });
      expect(() => repo.check('missing'), throwsA(isA<ApiServerFailure>()));
    });
  });
}
