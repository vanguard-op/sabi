import 'package:flutter/material.dart';

import '../design_system/sab_art.dart';
import '../design_system/tokens.dart';
import 'sab_button.dart';

/// The shared empty state (screens.md): a centred illustration, a headline, a
/// contextual subtitle, and one call to action.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.title,
    required this.message,
    this.actionLabel,
    this.onAction,
    this.illustration = SabArtboard.emptyState,
    this.semanticLabel,
  });

  final String title;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;
  final SabArtboard illustration;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(SabSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SabArt(
              artboard: illustration,
              size: SabSizes.artEmptyState,
              semanticLabel: semanticLabel,
            ),
            const SizedBox(height: SabSpacing.lg),
            Text(
              title,
              textAlign: TextAlign.center,
              style: SabTypography.h3.copyWith(color: colors.textPrimary),
            ),
            const SizedBox(height: SabSpacing.sm),
            Text(
              message,
              textAlign: TextAlign.center,
              style: SabTypography.bodySmall.copyWith(
                color: colors.textSecondary,
              ),
            ),
            if (actionLabel != null) ...[
              const SizedBox(height: SabSpacing.lg),
              SabButton(label: actionLabel!, onPressed: onAction),
            ],
          ],
        ),
      ),
    );
  }
}
