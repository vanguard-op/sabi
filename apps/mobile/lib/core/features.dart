import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Features the build can turn on or off. Each carries the durable FEAT id and
/// the roadmap phase that delivers it, so the UI can gate a surface without
/// naming a task or a route.
enum SabFeature {
  passwordlessOnboarding('FEAT-001', 1),
  intentUnderstanding('FEAT-003', 1),
  serviceDiscovery('FEAT-004', 1),
  composedSurfaces('FEAT-011', 1),
  providerRegistration('FEAT-012', 1),
  identityVerification('FEAT-002', 2),
  paymentAuthorization('FEAT-005', 2),
  receiptCapture('FEAT-008', 2),
  failureRecovery('FEAT-009', 2);

  const SabFeature(this.featId, this.phase);

  final String featId;
  final int phase;
}

/// The enabled feature set. Phase 1 ships onboarding, intent understanding,
/// discovery, and composed surfaces; later-phase payment surfaces stay gated and
/// render a neutral fallback until their phase lands.
@immutable
class SabFeatureFlags {
  const SabFeatureFlags(this.enabled);

  final Set<SabFeature> enabled;

  bool isEnabled(SabFeature feature) => enabled.contains(feature);

  bool get isPhase1 => enabled.contains(SabFeature.composedSurfaces);

  static const SabFeatureFlags phase1 = SabFeatureFlags({
    SabFeature.passwordlessOnboarding,
    SabFeature.intentUnderstanding,
    SabFeature.serviceDiscovery,
    SabFeature.composedSurfaces,
    SabFeature.providerRegistration,
  });
}

final featureFlagsProvider = Provider<SabFeatureFlags>(
  (ref) => SabFeatureFlags.phase1,
);
