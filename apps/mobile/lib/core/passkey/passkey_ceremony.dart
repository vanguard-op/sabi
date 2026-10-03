/// The platform authenticator behind the passkey ceremonies (FEAT-001).
///
/// The live repository drives the contract's two-step shape: it asks the
/// gateway for the WebAuthn options (C-001/C-003), hands them to the device
/// through this seam, then posts the credential back for verification
/// (C-002/C-004). Keeping the plugin behind an interface means the request and
/// response mapping and the unavailable fallback are unit-testable without a
/// device or a platform channel.
///
/// Implementations return the credential as the WebAuthn JSON the gateway
/// verifies: the attestation for [register], the assertion for [authenticate].
abstract class PasskeyCeremony {
  /// Whether this device can run a passkey ceremony.
  ///
  /// False means no platform authenticator is available, so onboarding offers
  /// the reduced-security recovery-code path instead (FEAT-001, screen 01).
  Future<bool> isSupported();

  /// Runs the registration ceremony against the C-001 creation options and
  /// returns the attestation credential for C-002.
  Future<Map<String, dynamic>> register(Map<String, dynamic> publicKey);

  /// Runs the assertion ceremony against the C-003 request options and returns
  /// the credential for C-004.
  Future<Map<String, dynamic>> authenticate(Map<String, dynamic> publicKey);
}

/// The device has no usable platform authenticator: no passkey can be enrolled
/// or asserted here. The caller falls back to the recovery-code path and says
/// so, rather than fabricating a credential (FEAT-001 edge case).
class PasskeyUnavailable implements Exception {
  const PasskeyUnavailable();

  @override
  String toString() => 'PasskeyUnavailable';
}

/// The ceremony ran but did not complete: the user dismissed the system prompt,
/// it timed out, or the authenticator rejected the request. Distinct from
/// [PasskeyUnavailable] so the caller retries the same path instead of
/// switching to the recovery-code fallback.
class PasskeyCeremonyFailure implements Exception {
  const PasskeyCeremonyFailure([this.message]);

  /// A short diagnostic reason; never user-facing copy.
  final String? message;

  @override
  String toString() => message ?? 'PasskeyCeremonyFailure';
}
