import 'package:flutter/material.dart';

import '../design_system/sab_art.dart';
import '../design_system/tokens.dart';
import 'sab_button.dart';

/// The shared error state (screens.md): a centred illustration, "Something went
/// wrong", a brief description, and a "Try again" primary action.
class ErrorState extends StatelessWidget {
  const ErrorState({
    super.key,
    required this.message,
    required this.retryLabel,
    required this.onRetry,
    this.title = 'Something went wrong',
  });

  final String title;
  final String message;
  final String retryLabel;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(SabSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SabArt(
              artboard: SabArtboard.error,
              size: SabSizes.artError,
              semanticLabel: 'Error',
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
            const SizedBox(height: SabSpacing.lg),
            SabButton(label: retryLabel, onPressed: onRetry),
          ],
        ),
      ),
    );
  }
}
