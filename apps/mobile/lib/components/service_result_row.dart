import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../design_system/icons.dart';
import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';
import '../models/service_summary.dart';

/// A discovery result (screens.md, "Service Result Row"): collecting body,
/// obligation, the known amount or "amount confirmed at payment", and a select
/// action. The selected background is `primary-300`.
class ServiceResultRow extends ConsumerWidget {
  const ServiceResultRow({
    super.key,
    required this.service,
    required this.onSelect,
    this.selected = false,
    this.selectLabel,
  });

  final ServiceSummary service;
  final VoidCallback onSelect;
  final bool selected;
  final String? selectLabel;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    final locale = ref.watch(localeProvider).code;
    final amountLabel = service.hasKnownAmount
        ? SabMoney.format(
            service.knownAmount!,
            currency: service.currency,
            locale: locale,
          )
        : strings.amountConfirmedAtPayment;

    return Semantics(
      button: true,
      selected: selected,
      label: '${service.collectingBody}, $amountLabel',
      child: Material(
        color: selected ? colors.primary300 : colors.surface,
        borderRadius: BorderRadius.circular(SabRadii.md),
        child: InkWell(
          onTap: onSelect,
          borderRadius: BorderRadius.circular(SabRadii.md),
          child: Container(
            padding: const EdgeInsets.all(SabSpacing.md),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(SabRadii.md),
              border: Border.all(
                color: selected ? colors.primary500 : colors.border,
              ),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        service.collectingBody,
                        style: SabTypography.body.copyWith(
                          color: colors.textPrimary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: SabSpacing.xs),
                      Text(
                        service.name,
                        style: SabTypography.bodySmall.copyWith(
                          color: colors.textSecondary,
                        ),
                      ),
                      const SizedBox(height: SabSpacing.xs),
                      Text(
                        amountLabel,
                        style: SabTypography.bodySmall.copyWith(
                          color: service.hasKnownAmount
                              ? colors.textPrimary
                              : colors.textSecondary,
                          fontWeight: service.hasKnownAmount
                              ? FontWeight.w600
                              : FontWeight.w400,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: SabSpacing.sm),
                if (selected)
                  SabIconView(
                    SabIcons.check,
                    size: SabSizes.iconMd,
                    color: colors.primary700,
                  )
                else
                  Text(
                    selectLabel ?? strings.selectService,
                    style: SabTypography.bodySmall.copyWith(
                      color: colors.primary500,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
