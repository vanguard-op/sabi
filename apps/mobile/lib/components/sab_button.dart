import 'package:flutter/material.dart';

import '../design_system/tokens.dart';

/// Button variants from branding.md ("Component Tokens"): one true primary
/// action per surface, secondary and outline for the rest, ghost for tertiary,
/// destructive kept secondary until its confirmation step.
enum SabButtonVariant { primary, secondary, outline, ghost, destructive }

/// The client's button. Renders one action, at the minimum touch target, with a
/// loading state that disables the action and announces itself.
class SabButton extends StatelessWidget {
  const SabButton({
    super.key,
    required this.label,
    this.onPressed,
    this.variant = SabButtonVariant.primary,
    this.loading = false,
    this.icon,
    this.expand = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final SabButtonVariant variant;
  final bool loading;
  final IconData? icon;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final enabled = onPressed != null && !loading;

    final (background, foreground, side) = switch (variant) {
      SabButtonVariant.primary => (colors.primary500, colors.onPrimary, null),
      SabButtonVariant.secondary => (
        colors.primary100,
        colors.primary700,
        null,
      ),
      SabButtonVariant.outline => (
        Colors.transparent,
        colors.primary500,
        BorderSide(color: colors.primary500, width: 1.5),
      ),
      SabButtonVariant.ghost => (
        Colors.transparent,
        colors.textSecondary,
        null,
      ),
      // The destructive fill is light red in dark mode, so the light-mode
      // knockout would fail WCAG AA there. The on-primary role token is white
      // on the light fill and deep green on the dark fill, readable in both.
      SabButtonVariant.destructive => (colors.error500, colors.onPrimary, null),
    };

    final content = loading
        ? SizedBox(
            width: SabSizes.iconMd,
            height: SabSizes.iconMd,
            child: CircularProgressIndicator(strokeWidth: 2, color: foreground),
          )
        : Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (icon != null) ...[
                Icon(icon, size: SabSizes.iconMd, color: foreground),
                const SizedBox(width: SabSpacing.sm),
              ],
              Flexible(
                child: Text(
                  label,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: SabTypography.body.copyWith(
                    color: foreground,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          );

    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(SabRadii.md),
    );
    final style = ButtonStyle(
      backgroundColor: WidgetStatePropertyAll(background),
      foregroundColor: WidgetStatePropertyAll(foreground),
      minimumSize: const WidgetStatePropertyAll(Size(0, SabSizes.buttonHeight)),
      padding: const WidgetStatePropertyAll(SabSizes.buttonPadding),
      elevation: const WidgetStatePropertyAll(0),
      shape: WidgetStatePropertyAll(shape),
      side: side == null ? null : WidgetStatePropertyAll(side),
      overlayColor: WidgetStatePropertyAll(foreground.withValues(alpha: 0.08)),
    );

    final button = switch (variant) {
      SabButtonVariant.outline => OutlinedButton(
        onPressed: enabled ? onPressed : null,
        style: style,
        child: content,
      ),
      SabButtonVariant.ghost => TextButton(
        onPressed: enabled ? onPressed : null,
        style: style,
        child: content,
      ),
      _ => ElevatedButton(
        onPressed: enabled ? onPressed : null,
        style: style,
        child: content,
      ),
    };

    return Semantics(
      button: true,
      enabled: enabled,
      label: loading ? '$label, loading' : label,
      excludeSemantics: true,
      child: expand ? SizedBox(width: double.infinity, child: button) : button,
    );
  }
}
