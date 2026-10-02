import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/empty_state.dart';
import '../../core/features.dart';
import '../../design_system/sab_art.dart';
import '../../l10n/sab_strings.dart';

/// The neutral fallback for a surface whose feature is not enabled yet. The
/// route, title, and back affordance still work, so a link into a gated screen
/// never dead-ends (feature gate, UI side).
class SabGatedScreen extends ConsumerWidget {
  const SabGatedScreen({
    super.key,
    required this.feature,
    required this.title,
    this.builder,
  });

  final SabFeature feature;
  final String title;

  /// The real surface once the feature ships. Null while the phase is pending.
  final WidgetBuilder? builder;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final flags = ref.watch(featureFlagsProvider);
    final enabled = flags.isEnabled(feature);
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        leading: BackButton(onPressed: () => context.pop()),
      ),
      body: enabled && builder != null
          ? builder!(context)
          : EmptyState(
              title: strings.notYetTitle,
              message: strings.notYetBody,
              illustration: SabArtboard.emptyState,
            ),
    );
  }
}
