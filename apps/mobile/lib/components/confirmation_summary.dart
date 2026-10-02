import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';

/// The confirmation summary block (screens.md): amount, payee, charges, and
/// reference in one block. The amount uses the `h2` token; the rest are
/// secondary text.
class ConfirmationSummary extends ConsumerWidget {
  const ConfirmationSummary({
    super.key,
    required this.amount,
    required this.currency,
    required this.payee,
    this.charges,
    this.reference,
  });

  /// Minor units (kobo).
  final int amount;
  final String currency;
  final String payee;
  final int? charges;
  final String? reference;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    final locale = ref.watch(localeProvider).code;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(SabSpacing.lg),
      decoration: BoxDecoration(
        color: colors.surfaceSecondary,
        borderRadius: BorderRadius.circular(SabRadii.lg),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            strings.amount,
            style: SabTypography.caption.copyWith(color: colors.textSecondary),
          ),
          const SizedBox(height: SabSpacing.xs),
          Text(
            SabMoney.format(amount, currency: currency, locale: locale),
            style: SabTypography.h2.copyWith(color: colors.textPrimary),
          ),
          const SizedBox(height: SabSpacing.md),
          _SummaryRow(label: strings.payee, value: payee),
          if (charges != null)
            _SummaryRow(
              label: strings.charges,
              value: SabMoney.format(
                charges!,
                currency: currency,
                locale: locale,
              ),
            ),
          if (reference != null && reference!.isNotEmpty)
            _SummaryRow(label: strings.reference, value: reference!),
        ],
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: SabSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: SabSizes.summaryLabelWidth,
            child: Text(
              label,
              style: SabTypography.bodySmall.copyWith(
                color: colors.textSecondary,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: SabTypography.body.copyWith(color: colors.textSecondary),
            ),
          ),
        ],
      ),
    );
  }
}
