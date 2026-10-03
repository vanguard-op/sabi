import '../core/api_client.dart';
import '../core/api_exception.dart';
import '../core/passkey/passkey_ceremony.dart';
import '../core/passkey/platform_passkey_ceremony.dart';
import '../l10n/sab_strings.dart';
import '../models/account.dart';
import 'repositories.dart';

export '../core/passkey/passkey_ceremony.dart'
    show PasskeyUnavailable, PasskeyCeremonyFailure;

/// Live authentication against the gateway (FEAT-001; C-001–C-007).
///
/// Registration and passkey sign-in follow the contract's two-step ceremony:
/// ask the gateway for the WebAuthn options, run the platform authenticator,
/// then post the credential back for verification. The device is bound through
/// [PasskeyCeremony], so the plugin (D-028) never leaks into this layer and the
/// mapping is testable without hardware.
///
/// A device with no platform authenticator raises [PasskeyUnavailable]; the
/// caller offers the reduced-security recovery-code path instead of pretending
/// a passkey exists. Recovery-code sign-in (C-005) is fully live and is the
/// route back in when the only passkey is lost.
class HttpAuthRepository implements AuthRepository {
  HttpAuthRepository(this._api, {PasskeyCeremony? ceremony})
    : _ceremony = ceremony ?? PlatformPasskeyCeremony();

  final SabApiClient _api;
  final PasskeyCeremony _ceremony;

  @override
  Future<bool> passkeySupported() async {
    try {
      return await _ceremony.isSupported();
    } catch (_) {
      // A probe that cannot answer is treated as unsupported, so onboarding
      // offers the recovery-code path rather than blocking on an error.
      return false;
    }
  }

  @override
  Future<RegistrationResult> createAccount({
    required AppLocale locale,
    required bool withPasskey,
  }) async {
    // The frozen contract's only registration path enrols a passkey (C-002); a
    // device that cannot host one cannot complete it, so be honest about that
    // instead of posting a credential that does not exist. The caller has
    // already shown the reduced-security recovery-code explanation.
    if (!withPasskey) throw const PasskeyUnavailable();

    final options = await _options('/auth/register/options', {
      'locale': locale.code,
    });
    final credential = await _ceremonyCredential(
      () => _ceremony.register(options.publicKey),
    );

    final Map<String, dynamic> body;
    try {
      body = await _api.post(
        '/auth/register/verify',
        body: {
          'challengeId': options.challengeId,
          'credential': credential,
          'displayName': null,
          'locale': locale.code,
        },
      );
    } on ApiConflict {
      // 409: the credential is already registered.
      throw const InvalidCredentialException();
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (error) {
      throw _verifyFailure(error);
    }

    final recoveryCode = body['recoveryCode'];
    if (recoveryCode is! String || recoveryCode.isEmpty) {
      throw const ApiServerFailure('The recovery code was not returned.');
    }
    return RegistrationResult(
      account: Account.fromJson(_user(body)),
      recoveryCode: recoveryCode,
    );
  }

  @override
  Future<Account> signInWithPasskey() async {
    final options = await _options('/auth/login/options');
    final credential = await _ceremonyCredential(
      () => _ceremony.authenticate(options.publicKey),
    );

    final Map<String, dynamic> body;
    try {
      body = await _api.post(
        '/auth/login/verify',
        body: {'challengeId': options.challengeId, 'credential': credential},
      );
    } on ApiUnauthenticated {
      // 401: no credential on the device matches the assertion.
      throw const InvalidCredentialException();
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (error) {
      throw _verifyFailure(error);
    }
    return Account.fromJson(_user(body));
  }

  @override
  Future<RecoverySignInResult> signInWithRecovery(String code) async {
    final Map<String, dynamic> body;
    try {
      body = await _api.post(
        '/auth/recovery/verify',
        body: {'recoveryCode': code},
      );
    } on ApiUnauthenticated {
      throw const InvalidCredentialException();
    } on ApiConflict {
      throw const InvalidCredentialException();
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (error) {
      throw ApiServerFailure(error.message);
    }
    return RecoverySignInResult(
      account: Account.fromJson(_user(body)),
      mustEnrolPasskey: body['mustEnrolPasskey'] != false,
    );
  }

  @override
  Future<void> signOut() async {
    // The end-user contract has no sign-out endpoint; the client clears its
    // session state and the cookie is dropped by the platform jar. A future
    // C-### logout is a drop-in change here.
    return;
  }

  /// Fetches a ceremony's `challengeId` and `publicKey` (C-001/C-003), mapping
  /// a gateway error to the shared failure the screen already understands.
  Future<({String challengeId, Map<String, dynamic> publicKey})> _options(
    String path, [
    Object? body,
  ]) async {
    final Map<String, dynamic> decoded;
    try {
      decoded = await _api.post(path, body: body);
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (error) {
      throw ApiServerFailure(error.message);
    }

    final challengeId = decoded['challengeId'];
    final publicKey = decoded['publicKey'];
    if (challengeId is! String || challengeId.isEmpty || publicKey is! Map) {
      throw const ApiServerFailure('The ceremony options were not valid.');
    }
    return (
      challengeId: challengeId,
      publicKey: publicKey.cast<String, dynamic>(),
    );
  }

  /// Runs a ceremony, letting the unavailable signal through so the caller can
  /// offer the fallback, and wrapping every other failure as retryable.
  Future<Map<String, dynamic>> _ceremonyCredential(
    Future<Map<String, dynamic>> Function() ceremony,
  ) async {
    try {
      return await ceremony();
    } on PasskeyUnavailable {
      rethrow;
    } on PasskeyCeremonyFailure {
      rethrow;
    } catch (_) {
      throw const PasskeyCeremonyFailure();
    }
  }

  static Exception _verifyFailure(ApiException error) =>
      switch (error.statusCode) {
        // 400 invalid credential or 410 expired challenge: the ceremony must be
        // run again, which is not a recovery-code fallback.
        400 || 410 => PasskeyCeremonyFailure(error.message),
        _ => ApiServerFailure(error.message),
      };

  static Map<String, dynamic> _user(Map<String, dynamic> body) {
    final user = body['user'];
    if (user is Map) return user.cast<String, dynamic>();
    // Defensive: an unexpected shape is a server failure, not a crash.
    throw const ApiException(
      statusCode: 200,
      code: 'malformed',
      message: 'The account record was not valid.',
    );
  }
}
