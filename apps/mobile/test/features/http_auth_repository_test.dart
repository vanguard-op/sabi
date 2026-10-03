import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sabi_mobile/core/api_client.dart';
import 'package:sabi_mobile/core/api_config.dart';
import 'package:sabi_mobile/core/passkey/passkey_ceremony.dart';
import 'package:sabi_mobile/data/http_auth_repository.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';

const _config = ApiConfig(baseUrl: 'http://10.0.2.2:8000/v1');

/// Answers by request path and keeps the bodies so the test can assert the
/// exact contract mapping the repository posts back.
class _RecordingClient extends http.BaseClient {
  _RecordingClient(this.responses);

  final Map<String, ({int status, Object body})> responses;
  final List<String> requestBodies = [];
  final List<String> requestPaths = [];

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

class _FakeCeremony implements PasskeyCeremony {
  bool supported = true;
  Object? registerFailure;
  Object? authenticateFailure;
  Map<String, dynamic>? lastCreationOptions;
  Map<String, dynamic>? lastRequestOptions;

  static const attestation = <String, dynamic>{
    'id': 'cred_1',
    'rawId': 'cred_1',
    'type': 'public-key',
    'response': {
      'clientDataJSON': 'attestation-client-data',
      'attestationObject': 'attestation-object',
    },
  };

  static const assertion = <String, dynamic>{
    'id': 'cred_1',
    'rawId': 'cred_1',
    'type': 'public-key',
    'response': {
      'clientDataJSON': 'assertion-client-data',
      'authenticatorData': 'auth-data',
      'signature': 'signature',
    },
  };

  @override
  Future<bool> isSupported() async => supported;

  @override
  Future<Map<String, dynamic>> register(Map<String, dynamic> publicKey) async {
    lastCreationOptions = publicKey;
    if (registerFailure != null) throw registerFailure!;
    return attestation;
  }

  @override
  Future<Map<String, dynamic>> authenticate(
    Map<String, dynamic> publicKey,
  ) async {
    lastRequestOptions = publicKey;
    if (authenticateFailure != null) throw authenticateFailure!;
    return assertion;
  }
}

Map<String, dynamic> _user() => {
  'id': 'acct_1',
  'displayName': null,
  'locale': 'en',
  'preferredChannel': 'app',
  'kycStatus': 'unverified',
  'accountStatus': 'active',
  'createdAt': '2026-10-01T00:00:00Z',
  'updatedAt': '2026-10-01T00:00:00Z',
};

HttpAuthRepository _repo(_RecordingClient client, _FakeCeremony ceremony) =>
    HttpAuthRepository(
      SabApiClient(config: _config, httpClient: client),
      ceremony: ceremony,
    );

void main() {
  group('registration (C-001, C-002)', () {
    test('maps the gateway options through the ceremony and posts them back', () async {
      final client = _RecordingClient({
        '/v1/auth/register/options': (
          status: 200,
          body: {
            'challengeId': 'ch_1',
            'publicKey': {
              'challenge': 'challenge-b64url',
              'rp': {'id': 'localhost', 'name': 'Sabi'},
              'user': {'id': 'dXNlcg', 'name': 'user_1', 'displayName': 'Sabi'},
            },
          },
        ),
        '/v1/auth/register/verify': (
          status: 201,
          body: {'user': _user(), 'recoveryCode': 'SABI-4F9K-2Q7M-88XD'},
        ),
      });
      final ceremony = _FakeCeremony();

      final result = await _repo(
        client,
        ceremony,
      ).createAccount(locale: AppLocale.english, withPasskey: true);

      // The creation options the gateway minted reach the authenticator intact.
      expect(ceremony.lastCreationOptions?['challenge'], 'challenge-b64url');
      expect(ceremony.lastCreationOptions?['rp'], isA<Map>());

      // C-002 carries the challenge id, the attestation, no display name, and
      // the locale; the plugin response is sent verbatim as the credential.
      final verifyBody =
          jsonDecode(client.requestBodies.last) as Map<String, dynamic>;
      expect(verifyBody['challengeId'], 'ch_1');
      expect(verifyBody['credential'], _FakeCeremony.attestation);
      expect(verifyBody['displayName'], isNull);
      expect(verifyBody['locale'], 'en');

      expect(result.account.id, 'acct_1');
      expect(result.recoveryCode, 'SABI-4F9K-2Q7M-88XD');
    });

    test('an already-registered credential is an invalid credential', () {
      final client = _RecordingClient({
        '/v1/auth/register/options': (
          status: 200,
          body: {'challengeId': 'ch_1', 'publicKey': <String, dynamic>{}},
        ),
        '/v1/auth/register/verify': (
          status: 409,
          body: {
            'error': {'code': 'conflict', 'message': 'Already registered.'},
          },
        ),
      });
      expect(
        () => _repo(
          client,
          _FakeCeremony(),
        ).createAccount(locale: AppLocale.english, withPasskey: true),
        throwsA(isA<InvalidCredentialException>()),
      );
    });

    test(
      'an expired challenge asks for a fresh ceremony, not the fallback',
      () {
        final client = _RecordingClient({
          '/v1/auth/register/options': (
            status: 200,
            body: {'challengeId': 'ch_1', 'publicKey': <String, dynamic>{}},
          ),
          '/v1/auth/register/verify': (
            status: 410,
            body: {
              'error': {'code': 'challenge_expired', 'message': 'Expired.'},
            },
          ),
        });
        expect(
          () => _repo(
            client,
            _FakeCeremony(),
          ).createAccount(locale: AppLocale.english, withPasskey: true),
          throwsA(isA<PasskeyCeremonyFailure>()),
        );
      },
    );
  });

  group('passkey sign-in (C-003, C-004)', () {
    test(
      'maps the request options through the ceremony and posts the assertion',
      () async {
        final client = _RecordingClient({
          '/v1/auth/login/options': (
            status: 200,
            body: {
              'challengeId': 'ch_2',
              'publicKey': {
                'challenge': 'challenge-b64url',
                'rpId': 'localhost',
              },
            },
          ),
          '/v1/auth/login/verify': (status: 200, body: {'user': _user()}),
        });
        final ceremony = _FakeCeremony();

        final account = await _repo(client, ceremony).signInWithPasskey();

        expect(ceremony.lastRequestOptions?['rpId'], 'localhost');
        final verifyBody =
            jsonDecode(client.requestBodies.last) as Map<String, dynamic>;
        expect(verifyBody['challengeId'], 'ch_2');
        expect(verifyBody['credential'], _FakeCeremony.assertion);
        expect(account.id, 'acct_1');
      },
    );

    test('a rejected assertion is an invalid credential', () {
      final client = _RecordingClient({
        '/v1/auth/login/options': (
          status: 200,
          body: {'challengeId': 'ch_2', 'publicKey': <String, dynamic>{}},
        ),
        '/v1/auth/login/verify': (
          status: 401,
          body: {
            'error': {'code': 'unauthenticated', 'message': 'No match.'},
          },
        ),
      });
      expect(
        () => _repo(client, _FakeCeremony()).signInWithPasskey(),
        throwsA(isA<InvalidCredentialException>()),
      );
    });
  });

  group('unavailable fallback (FEAT-001 edge case)', () {
    test('a probe failure reports unsupported', () async {
      final ceremony = _FakeCeremony()..supported = false;
      final client = _RecordingClient({});
      expect(await _repo(client, ceremony).passkeySupported(), isFalse);
    });

    test(
      'the reduced-security path raises PasskeyUnavailable before any call',
      () async {
        final client = _RecordingClient({});
        final ceremony = _FakeCeremony();
        expect(
          () => _repo(
            client,
            ceremony,
          ).createAccount(locale: AppLocale.english, withPasskey: false),
          throwsA(isA<PasskeyUnavailable>()),
        );
        expect(client.requestPaths, isEmpty);
      },
    );

    test(
      'a device that cannot create a credential raises PasskeyUnavailable',
      () async {
        final client = _RecordingClient({
          '/v1/auth/register/options': (
            status: 200,
            body: {'challengeId': 'ch_1', 'publicKey': <String, dynamic>{}},
          ),
        });
        final ceremony = _FakeCeremony()
          ..registerFailure = const PasskeyUnavailable();
        await expectLater(
          _repo(
            client,
            ceremony,
          ).createAccount(locale: AppLocale.english, withPasskey: true),
          throwsA(isA<PasskeyUnavailable>()),
        );
        // The ceremony stopping means C-002 is never attempted.
        expect(client.requestPaths, ['/v1/auth/register/options']);
      },
    );

    test('a device that cannot assert raises PasskeyUnavailable', () async {
      final client = _RecordingClient({
        '/v1/auth/login/options': (
          status: 200,
          body: {'challengeId': 'ch_2', 'publicKey': <String, dynamic>{}},
        ),
      });
      final ceremony = _FakeCeremony()
        ..authenticateFailure = const PasskeyUnavailable();
      await expectLater(
        _repo(client, ceremony).signInWithPasskey(),
        throwsA(isA<PasskeyUnavailable>()),
      );
      expect(client.requestPaths, ['/v1/auth/login/options']);
    });

    test('a cancelled ceremony is retryable, not the fallback', () async {
      final client = _RecordingClient({
        '/v1/auth/login/options': (
          status: 200,
          body: {'challengeId': 'ch_2', 'publicKey': <String, dynamic>{}},
        ),
      });
      final ceremony = _FakeCeremony()
        ..authenticateFailure = const PasskeyCeremonyFailure('cancelled');
      await expectLater(
        _repo(client, ceremony).signInWithPasskey(),
        throwsA(isA<PasskeyCeremonyFailure>()),
      );
    });
  });
}
