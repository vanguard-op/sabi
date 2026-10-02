import 'package:flutter/material.dart';

import '../design_system/tokens.dart';

/// A titled group used for Account's profile, verification, channels, and
/// methods sections. It keeps those groups on the same surface and spacing
/// tokens rather than each list reinventing its container.
class SectionCard extends StatelessWidget {
  const SectionCard({
    super.key,
    required this.title,
    required this.children,
    this.trailing,
  });

  final String title;
  final List<Widget> children;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(SabRadii.md),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title.toUpperCase(),
                  style: SabTypography.caption.copyWith(
                    color: colors.textSecondary,
                  ),
                ),
              ),
              ?trailing,
            ],
          ),
          const SizedBox(height: SabSpacing.sm),
          ...children,
        ],
      ),
    );
  }
}

/// A single label/value row used inside a [SectionCard].
class SectionRow extends StatelessWidget {
  const SectionRow({
    super.key,
    required this.label,
    required this.value,
    this.valueWidget,
    this.onTap,
    this.icon,
  });

  final String label;
  final String value;
  final Widget? valueWidget;
  final VoidCallback? onTap;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(SabRadii.sm),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: SabSizes.minTouchTarget),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: SabSpacing.sm),
          child: Row(
            children: [
              if (icon != null) ...[
                Icon(icon, size: SabSizes.iconMd, color: colors.textSecondary),
                const SizedBox(width: SabSpacing.sm),
              ],
              Expanded(
                child: Text(
                  label,
                  style: SabTypography.body.copyWith(color: colors.textPrimary),
                ),
              ),
              const SizedBox(width: SabSpacing.sm),
              valueWidget ??
                  Text(
                    value,
                    style: SabTypography.bodySmall.copyWith(
                      color: colors.textSecondary,
                    ),
                  ),
            ],
          ),
        ),
      ),
    );
  }
}
