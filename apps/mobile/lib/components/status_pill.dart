import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../design_system/icons.dart';
import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';

/// The states a Status Pill can show (screens.md, "Status Pill").
enum SabStatus {
  pending,
  settled,
  failed,
  awaitingReceipt,
  unverified,
  verified,
  suspended,
}

/// A status badge that pairs a semantic colour with an icon and a text label.
/// Colour is never the only signal (branding.md, "Accessibility").
class StatusPill extends ConsumerWidget {
  const StatusPill({super.key, required this.status, this.label});

  final SabStatus status;

  /// Overrides the default label; used where the surface carries the wording.
  final String? label;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    final resolved = label ?? _defaultLabel(strings);

    final (background, foreground, icon) = switch (status) {
      SabStatus.pending => (
        colors.warning100,
        colors.warning900,
        SabIcons.statusPending,
      ),
      SabStatus.settled => (
        colors.success100,
        colors.success900,
        SabIcons.statusSettled,
      ),
      SabStatus.failed => (
        colors.error100,
        colors.error900,
        SabIcons.statusFailed,
      ),
      SabStatus.awaitingReceipt => (
        colors.info100,
        colors.info900,
        SabIcons.statusAwaitingReceipt,
      ),
      SabStatus.unverified => (
        colors.warning100,
        colors.warning900,
        SabIcons.statusUnverified,
      ),
      SabStatus.verified => (
        colors.success100,
        colors.success900,
        SabIcons.statusVerified,
      ),
      SabStatus.suspended => (
        colors.error100,
        colors.error900,
        SabIcons.statusSuspended,
      ),
    };

    return Semantics(
      label: resolved,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: SabSpacing.sm,
          vertical: SabSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(SabRadii.full),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SabIconView(icon, size: SabSizes.iconSm, color: foreground),
            const SizedBox(width: SabSpacing.xs),
            Text(
              resolved,
              style: SabTypography.caption.copyWith(color: foreground),
            ),
          ],
        ),
      ),
    );
  }

  String _defaultLabel(SabStrings s) => switch (status) {
    SabStatus.pending => s.statusPending,
    SabStatus.settled => s.statusSettled,
    SabStatus.failed => s.statusFailed,
    SabStatus.awaitingReceipt => s.statusAwaitingReceipt,
    SabStatus.unverified => s.statusUnverified,
    SabStatus.verified => s.statusVerified,
    SabStatus.suspended => s.statusSuspended,
  };
}
