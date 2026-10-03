import 'dart:convert';

import '../../../core/api_client.dart';
import '../../../core/api_exception.dart';
import '../../../l10n/sab_strings.dart';
import '../../../models/account.dart';
import '../../payment/models/payment_errors.dart';
import 'repositories.dart';

/// Live authentication against the gateway (FEAT-001; C-001–C-007).
///
/// The passkey ceremony itself is the platform authenticator's, reached through
/// a platform channel that Phase 2 does not yet bind. Until it is, the live
/// repository drives the contract's two-step shape with an explicit
/// "passkey unavailable" result rather than fabricating an attestation: a screen
/// showing the reduced-security recovery-code path is honest about the device.
/// [createAccount] and [signInWithPasskey] therefore raise [PasskeyUnavailable],
/// which the UI maps to the recovery path; recovery-code sign-in is fully live.
class HttpAuthRepository implements AuthRepository {
  HttpAuthRepository(this._api);

  final SabApiClient _api;

  @override
  Future<bool> passkeySupported() async {
    // The client cannot verify a platform authenticator without the passkey
    // channel; report unsupported so onboarding offers the recovery-code path.
    return false;
  }

  @override
  Future<RegistrationResult> createAccount({
    required AppLocale locale,
    required bool withPasskey,
  }) async {
    // Fetch the ceremony options to prove the gateway is reachable and the
    // contract shape intact (C-001); the ceremony cannot be completed without
    // the platform channel, so registration stops here with a stated reason.
    try {
      await _api.post('/auth/register/options', body: {'locale': locale.code});
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    } on ApiUnreachable {
      rethrow;
    }
    throw const PasskeyUnavailable();
  }

  @override
  Future<Account> signInWithPasskey() async {
    try {
      await _api.post('/auth/login/options');
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    } on ApiUnreachable {
      rethrow;
    }
    throw const PasskeyUnavailable();
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
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
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

/// The platform authenticator is not yet bound (see [HttpAuthRepository]);
/// onboarding falls back to the recovery-code path.
class PasskeyUnavailable implements Exception {
  const PasskeyUnavailable();
}

/// A gateway error the caller can retry; distinct from a transport failure so
/// the screen can show an inline retry rather than the offline banner.
class ApiServerFailure implements Exception {
  const ApiServerFailure(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Serialises a WebAuthn credential for a future passkey channel. Kept here so
/// the ceremony payload and the contract fields live together.
String encodeCredential(Map<String, dynamic> credential) =>
    jsonEncode(credential);
