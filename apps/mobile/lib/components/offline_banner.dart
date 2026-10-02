import 'package:flutter/material.dart';

import '../design_system/icons.dart';
import '../design_system/tokens.dart';

/// The persistent offline banner (screens.md). It states what is queued and its
/// sync status; no payment can be authorised while it is shown. It is a live
/// region so a screen reader announces the state change.
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({super.key, required this.message, this.queuedLabel});

  final String message;

  /// Optional line naming what is queued and its sync status.
  final String? queuedLabel;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Semantics(
      liveRegion: true,
      container: true,
      child: Container(
        width: double.infinity,
        color: colors.warning100,
        padding: const EdgeInsets.symmetric(
          horizontal: SabSpacing.md,
          vertical: SabSpacing.sm,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SabIconView(
              SabIcons.offline,
              size: SabSizes.iconSm,
              color: colors.warning700,
            ),
            const SizedBox(width: SabSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    message,
                    style: SabTypography.bodySmall.copyWith(
                      color: colors.warning900,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (queuedLabel != null)
                    Text(
                      queuedLabel!,
                      style: SabTypography.caption.copyWith(
                        color: colors.warning900,
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
