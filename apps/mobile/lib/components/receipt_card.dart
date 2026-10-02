import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../design_system/icons.dart';
import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';
import '../models/receipt_summary.dart';
import 'status_pill.dart';

/// A recent receipt shown on Home and Receipts (screens.md, "Receipt Card"):
/// reference, payee, amount, date, and kind, and it opens Receipt Detail.
class ReceiptCard extends ConsumerWidget {
  const ReceiptCard({super.key, required this.receipt, this.onTap});

  final ReceiptSummary receipt;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final locale = ref.watch(localeProvider).code;
    return Semantics(
      button: onTap != null,
      label:
          '${receipt.payee}, ${SabMoney.format(receipt.amount, currency: receipt.currency, locale: locale)}',
      child: Material(
        color: colors.surface,
        borderRadius: BorderRadius.circular(SabRadii.md),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(SabRadii.md),
          child: Container(
            padding: const EdgeInsets.all(SabSpacing.md),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(SabRadii.md),
              border: Border.all(color: colors.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            receipt.payee,
                            style: SabTypography.body.copyWith(
                              color: colors.textPrimary,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: SabSpacing.xs),
                          Text(
                            '${receipt.kind} · ${receipt.reference}',
                            style: SabTypography.bodySmall.copyWith(
                              color: colors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: SabSpacing.sm),
                    Text(
                      SabMoney.format(
                        receipt.amount,
                        currency: receipt.currency,
                        locale: locale,
                      ),
                      style: SabTypography.body.copyWith(
                        color: colors.textPrimary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: SabSpacing.md),
                Row(
                  children: [
                    StatusPill(
                      status: switch (receipt.status) {
                        PaymentStatus.pending => SabStatus.pending,
                        PaymentStatus.settled => SabStatus.settled,
                        PaymentStatus.failed => SabStatus.failed,
                        PaymentStatus.awaitingReceipt =>
                          SabStatus.awaitingReceipt,
                      },
                    ),
                    const Spacer(),
                    Text(
                      SabMoney.formatDate(receipt.issuedAt, locale: locale),
                      style: SabTypography.bodySmall.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                    if (onTap != null) ...[
                      const SizedBox(width: SabSpacing.xs),
                      SabIconView(
                        SabIcons.chevronRight,
                        size: SabSizes.iconSm,
                        color: colors.textSecondary,
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
