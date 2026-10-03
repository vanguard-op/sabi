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

/// Why no passkey ceremony can run, so the screen can be specific about the
/// cause instead of blaming the user (FEAT-001 edge case; screens/01-welcome).
enum PasskeyUnavailableReason {
  /// The platform has no usable authenticator: an old OS, or no credential
  /// provider enabled. The reduced-security recovery-code path applies.
  noAuthenticator,

  /// The relying-party origin is not associated with this build, so the OS
  /// refuses the ceremony before any credential is made (`DomainNotAssociated`
  /// on the plugin). A setup problem in the build or the RP, not the user's
  /// data being rejected; the recovery-code path is the way forward.
  domainNotAssociated,
}

/// The device or relying party cannot host a passkey ceremony: no passkey can be
/// enrolled or asserted here. The caller falls back to the recovery-code path
/// and says why, rather than fabricating a credential (FEAT-001 edge case).
class PasskeyUnavailable implements Exception {
  const PasskeyUnavailable([
    this.reason = PasskeyUnavailableReason.noAuthenticator,
  ]);

  /// The cause, so the screen distinguishes a device without an authenticator
  /// from a build whose relying party is not set up.
  final PasskeyUnavailableReason reason;

  @override
  String toString() => 'PasskeyUnavailable($reason)';
}

/// Why a ceremony that started did not complete: either the user stepped away
/// (quietly, not an error) or something worth retrying failed.
enum PasskeyFailureReason {
  /// The user dismissed the system sheet. Not an error: return quietly to the
  /// ready state, never to a failure banner.
  cancelled,

  /// The system prompt timed out before a credential was produced.
  timeout,

  /// The authenticator reported a case the plugin does not classify.
  unhandled,

  /// Options the platform could not parse; a fresh ceremony is a meaningful
  /// retry, unlike the recovery-code fallback.
  malformed,

  /// The gateway rejected the credential and asked for a fresh ceremony
  /// (C-002/C-004 `400`/`410`).
  verification,

  /// Any other failure on the same path.
  other,
}

/// The ceremony ran but did not complete: the user dismissed the system prompt,
/// it timed out, or the authenticator rejected the request. Distinct from
/// [PasskeyUnavailable] so the caller retries the same path instead of
/// switching to the recovery-code fallback, and carries a [reason] so the
/// screen branches on the outcome rather than matching strings.
class PasskeyCeremonyFailure implements Exception {
  const PasskeyCeremonyFailure([
    this.message,
    this.reason = PasskeyFailureReason.other,
  ]);

  /// A short diagnostic reason; never user-facing copy.
  final String? message;

  /// The classified outcome, so the caller can treat a cancellation quietly
  /// and offer a retry only when a retry is meaningful.
  final PasskeyFailureReason reason;

  @override
  String toString() => message ?? 'PasskeyCeremonyFailure($reason)';
}
