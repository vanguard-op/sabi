import 'package:flutter_test/flutter_test.dart';
import 'package:passkeys/authenticator.dart';
import 'package:passkeys/types.dart';
import 'package:sabi_mobile/core/passkey/passkey_ceremony.dart';
import 'package:sabi_mobile/core/passkey/platform_passkey_ceremony.dart';

/// A [PasskeyAuthenticator] stand-in that records the framed request and returns
/// or throws what the test asks for, so the plugin boundary is exercised without
/// a device.
class _FakeAuthenticator extends PasskeyAuthenticator {
  _FakeAuthenticator() : super(debugMode: false);

  Object? registerError;
  Object? authenticateError;
  RegisterRequestType? lastRegister;
  AuthenticateRequestType? lastAuthenticate;

  static const registerResponse = RegisterResponseType(
    id: 'cred_1',
    rawId: 'cred_1',
    clientDataJSON: 'client-data',
    attestationObject: 'attestation',
    transports: ['internal'],
  );

  static const authenticateResponse = AuthenticateResponseType(
    id: 'cred_1',
    rawId: 'cred_1',
    clientDataJSON: 'client-data',
    authenticatorData: 'auth-data',
    signature: 'signature',
    userHandle: '',
  );

  @override
  Future<RegisterResponseType> register(RegisterRequestType request) async {
    lastRegister = request;
    if (registerError != null) throw registerError!;
    return registerResponse;
  }

  @override
  Future<AuthenticateResponseType> authenticate(
    AuthenticateRequestType request,
  ) async {
    lastAuthenticate = request;
    if (authenticateError != null) throw authenticateError!;
    return authenticateResponse;
  }
}

Map<String, dynamic> _creationOptions() => {
  'challenge': 'challenge-b64url',
  'rp': {'id': 'localhost', 'name': 'Sabi'},
  'user': {'id': 'dXNlcg', 'name': 'user_1', 'displayName': 'Sabi'},
};

Map<String, dynamic> _requestOptions() => {
  'challenge': 'challenge-b64url',
  'rpId': 'localhost',
};

void main() {
  group('registration framing', () {
    test(
      'parses the C-001 options and returns the plugin credential',
      () async {
        final authenticator = _FakeAuthenticator();
        final ceremony = PlatformPasskeyCeremony(authenticator: authenticator);

        final credential = await ceremony.register(_creationOptions());

        expect(authenticator.lastRegister?.challenge, 'challenge-b64url');
        expect(authenticator.lastRegister?.relyingParty.id, 'localhost');
        expect(credential, _FakeAuthenticator.registerResponse.toJson());
        // The backend receives the standard WebAuthn shape.
        expect(credential['type'], 'public-key');
        expect(
          (credential['response'] as Map)['attestationObject'],
          'attestation',
        );
      },
    );
  });

  group('authentication framing', () {
    test('parses the C-003 options and returns the plugin assertion', () async {
      final authenticator = _FakeAuthenticator();
      final ceremony = PlatformPasskeyCeremony(authenticator: authenticator);

      final credential = await ceremony.authenticate(_requestOptions());

      expect(authenticator.lastAuthenticate?.challenge, 'challenge-b64url');
      expect(authenticator.lastAuthenticate?.relyingPartyId, 'localhost');
      expect(credential, _FakeAuthenticator.authenticateResponse.toJson());
      expect((credential['response'] as Map)['signature'], 'signature');
    });
  });

  group('failure normalisation', () {
    test('an unsupported device is the unavailable fallback', () async {
      final authenticator = _FakeAuthenticator()
        ..registerError = PasskeyUnsupportedException();
      final ceremony = PlatformPasskeyCeremony(authenticator: authenticator);
      await expectLater(
        ceremony.register(_creationOptions()),
        throwsA(isA<PasskeyUnavailable>()),
      );
    });

    test('no credential on the device is the unavailable fallback', () async {
      final authenticator = _FakeAuthenticator()
        ..authenticateError = NoCredentialsAvailableException();
      final ceremony = PlatformPasskeyCeremony(authenticator: authenticator);
      await expectLater(
        ceremony.authenticate(_requestOptions()),
        throwsA(isA<PasskeyUnavailable>()),
      );
    });

    test(
      'a cancelled prompt is a quiet cancellation, not the fallback',
      () async {
        final authenticator = _FakeAuthenticator()
          ..authenticateError = PasskeyAuthCancelledException();
        final ceremony = PlatformPasskeyCeremony(authenticator: authenticator);
        await expectLater(
          ceremony.authenticate(_requestOptions()),
          throwsA(
            isA<PasskeyCeremonyFailure>().having(
              (error) => error.reason,
              'reason',
              PasskeyFailureReason.cancelled,
            ),
          ),
        );
      },
    );

    test('unparseable options are retryable, not the fallback', () async {
      final ceremony = PlatformPasskeyCeremony(
        authenticator: _FakeAuthenticator(),
      );
      await expectLater(
        ceremony.register({'challenge': 'x'}),
        throwsA(isA<PasskeyCeremonyFailure>()),
      );
    });
  });
}
