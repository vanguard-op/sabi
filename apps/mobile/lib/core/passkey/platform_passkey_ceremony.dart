import 'package:flutter/foundation.dart';
import 'package:passkeys/authenticator.dart';
import 'package:passkeys/types.dart';

import 'passkey_ceremony.dart';

/// Binds the `passkeys` plugin (Corbado) to [PasskeyCeremony] (D-028).
///
/// The plugin validates and frames the WebAuthn options the gateway already
/// minted, then runs the OS prompt; the self-hosted relying party (D-004) stays
/// the verifier. The relying-party id and origin are the server's
/// (`webauthn_rp_id` / `webauthn_origin`) and are never rewritten here, so the
/// ceremony cannot drift from what the backend expects.
///
/// Requirements this class depends on, configured outside Dart:
/// - iOS: the `webcredentials:<webauthn_rp_id>` associated-domain entitlement
///   plus the matching Apple App Site Association file on the RP origin.
/// - Android: Digital Asset Links on the RP origin naming the app package and
///   signing certificate (see `android/app/src/main/AndroidManifest.xml`).
class PlatformPasskeyCeremony implements PasskeyCeremony {
  PlatformPasskeyCeremony({PasskeyAuthenticator? authenticator})
    : _authenticator = authenticator ?? PasskeyAuthenticator();

  final PasskeyAuthenticator _authenticator;

  @override
  Future<bool> isSupported() async {
    try {
      return switch (defaultTargetPlatform) {
        TargetPlatform.android =>
          (await _authenticator.getAvailability().android()).hasPasskeySupport,
        TargetPlatform.iOS =>
          (await _authenticator.getAvailability().iOS()).hasPasskeySupport,
        // The app ships on Android and iOS only; anywhere else there is no
        // platform authenticator to bind.
        _ => false,
      };
    } catch (_) {
      // A failed capability probe is reported as unsupported so onboarding
      // offers the recovery-code path instead of blocking on an error.
      return false;
    }
  }

  @override
  Future<Map<String, dynamic>> register(Map<String, dynamic> publicKey) =>
      _guard(() async {
        // Parsing the gateway's options is part of the ceremony: malformed
        // options are a retryable failure, not the unavailable fallback.
        final request = RegisterRequestType.fromJson(publicKey);
        return (await _authenticator.register(request)).toJson();
      });

  @override
  Future<Map<String, dynamic>> authenticate(Map<String, dynamic> publicKey) =>
      _guard(() async {
        final request = AuthenticateRequestType.fromJson(
          publicKey,
          // Discoverable-credential sign-in: the device's passkey is presented
          // directly, and security keys are not offered because the relying
          // party never registers this account on one for the app flow.
          mediation: MediationType.Optional,
          preferImmediatelyAvailableCredentials: true,
          canBeSecurityKey: false,
        );
        return (await _authenticator.authenticate(request)).toJson();
      });

  /// Runs a ceremony and normalises the plugin's failures into the seam's
  /// typed outcomes: a device or relying party that cannot host a credential
  /// becomes [PasskeyUnavailable] (the fallback trigger, with its [reason]); a
  /// user cancellation and a retryable failure both become a
  /// [PasskeyCeremonyFailure] distinguished by [PasskeyFailureReason].
  Future<Map<String, dynamic>> _guard(
    Future<Map<String, dynamic>> Function() ceremony,
  ) async {
    try {
      return await ceremony();
    } on PasskeyUnsupportedException {
      throw const PasskeyUnavailable();
    } on DeviceNotSupportedException {
      throw const PasskeyUnavailable();
    } on NoCreateOptionException {
      throw const PasskeyUnavailable();
    } on NoCredentialsAvailableException {
      throw const PasskeyUnavailable();
    } on DomainNotAssociatedException {
      // The RP origin is not associated with this build, so the OS refuses the
      // ceremony before a credential exists. A setup problem, not a rejected
      // user; the recovery-code path is the honest fallback.
      throw const PasskeyUnavailable(
        PasskeyUnavailableReason.domainNotAssociated,
      );
    } on PasskeyAuthCancelledException {
      // The user dismissed the sheet: not an error, so the caller returns to
      // the ready state rather than showing a failure.
      throw const PasskeyCeremonyFailure(null, PasskeyFailureReason.cancelled);
    } on TimeoutException catch (error) {
      throw PasskeyCeremonyFailure(error.message, PasskeyFailureReason.timeout);
    } on UnhandledAuthenticatorException catch (error) {
      throw PasskeyCeremonyFailure(
        error.message,
        PasskeyFailureReason.unhandled,
      );
    } on AuthenticatorException catch (error) {
      throw PasskeyCeremonyFailure(error.toString());
    } on FormatException catch (error) {
      // The gateway sent options the platform could not parse; a retry is
      // meaningful, a recovery-code fallback is not.
      throw PasskeyCeremonyFailure(
        error.message,
        PasskeyFailureReason.malformed,
      );
    } on ArgumentError catch (error) {
      throw PasskeyCeremonyFailure(
        error.message?.toString(),
        PasskeyFailureReason.malformed,
      );
    }
  }
}
