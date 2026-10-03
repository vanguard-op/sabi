import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/error_state.dart';
import '../../components/sab_button.dart';
import '../../components/section_card.dart';
import '../../components/skeleton.dart';
import '../../components/status_pill.dart';
import '../../core/money.dart';
import '../../data/providers.dart';
import '../../data/repositories.dart';
import '../../design_system/icons.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import '../../models/receipt.dart';
import 'receipts_controller.dart';

/// Screen 7: Receipt Detail (`/receipts/:receiptId`). Shows one receipt with
/// its official identifier and verification state, and lets the user share,
/// export, or raise a dispute. Covers loading, loaded, awaiting receipt,
/// verified, unverified, and error (screens/07-receipt-detail.md).
class ReceiptDetailScreen extends ConsumerStatefulWidget {
  const ReceiptDetailScreen({super.key, required this.receiptId});

  final String receiptId;

  @override
  ConsumerState<ReceiptDetailScreen> createState() =>
      _ReceiptDetailScreenState();
}

class _ReceiptDetailScreenState extends ConsumerState<ReceiptDetailScreen> {
  bool _documentBusy = false;
  bool _disputeBusy = false;

  /// Opens the case for this payment. A case is keyed by its own id (C-027), so
  /// the list is searched for the payment and the matching case is opened; when
  /// none exists the user is told rather than sent to a dead route.
  Future<void> _openDispute(ReceiptPayment payment) async {
    final strings = ref.read(sabStringsProvider);
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    setState(() => _disputeBusy = true);
    try {
      final page = await ref.read(casesRepositoryProvider).list();
      final match = page.cases
          .where((c) => c.paymentId == payment.paymentId)
          .firstOrNull;
      if (match == null) {
        messenger.showSnackBar(
          SnackBar(content: Text(strings.caseNotFound)),
        );
        return;
      }
      router.push('/cases/${match.caseId}');
    } catch (_) {
      messenger.showSnackBar(SnackBar(content: Text(strings.somethingWrong)));
    } finally {
      if (mounted) setState(() => _disputeBusy = false);
    }
  }

  Future<void> _onExport(ReceiptDetail detail) async {
    final strings = ref.read(sabStringsProvider);
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _documentBusy = true);
    try {
      await ref
          .read(receiptsRepositoryProvider)
          .document(widget.receiptId);
      messenger.showSnackBar(
        SnackBar(content: Text(strings.receiptExportReady)),
      );
    } on ReceiptDocumentPendingException {
      messenger.showSnackBar(
        SnackBar(content: Text(strings.receiptDocumentPending)),
      );
    } catch (_) {
      messenger.showSnackBar(
        SnackBar(content: Text(strings.receiptDocumentFailed)),
      );
    } finally {
      if (mounted) setState(() => _documentBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = ref.watch(sabStringsProvider);
    final async = ref.watch(receiptDetailProvider(widget.receiptId));

    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.pop()),
        title: Text(strings.receiptDetailTitle),
      ),
      body: async.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(SabSpacing.md),
          child: SabSkeletonList(rows: 3),
        ),
        error: (_, _) => ErrorState(
          message: strings.receiptNotFound,
          retryLabel: strings.retry,
          onRetry: () =>
              ref.invalidate(receiptDetailProvider(widget.receiptId)),
        ),
        data: (detail) => _ReceiptBody(
          detail: detail,
          strings: strings,
          documentBusy: _documentBusy,
          disputeBusy: _disputeBusy,
          onExport: () => _onExport(detail),
          onDispute: () => _openDispute(detail.payment),
        ),
      ),
    );
  }
}

class _ReceiptBody extends ConsumerWidget {
  const _ReceiptBody({
    required this.detail,
    required this.strings,
    required this.documentBusy,
    required this.disputeBusy,
    required this.onExport,
    required this.onDispute,
  });

  final ReceiptDetail detail;
  final SabStrings strings;
  final bool documentBusy;
  final bool disputeBusy;
  final VoidCallback onExport;
  final VoidCallback onDispute;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final locale = ref.watch(localeProvider).code;
    final receipt = detail.receipt;
    final payment = detail.payment;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(SabSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // The receipt block: payee, amount, reference, date, and the official
          // identifier with its verification line where it applies.
          Container(
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
                  _kindLabel(strings, receipt.kind),
                  style: SabTypography.caption.copyWith(
                    color: colors.textSecondary,
                  ),
                ),
                const SizedBox(height: SabSpacing.xs),
                Text(
                  SabMoney.format(
                    payment.amount,
                    currency: payment.currency,
                    locale: locale,
                  ),
                  style: SabTypography.h1.copyWith(color: colors.textPrimary),
                ),
                const SizedBox(height: SabSpacing.md),
                _DetailRow(
                  label: strings.receiptPayeeLabel,
                  value: payment.payee,
                ),
                _DetailRow(
                  label: strings.receiptReferenceLabel,
                  value: payment.paymentId,
                ),
                if (receipt.issuedAt != null)
                  _DetailRow(
                    label: strings.receiptDateLabel,
                    value: SabMoney.formatDate(
                      receipt.issuedAt!,
                      locale: locale,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: SabSpacing.md),
          StatusPill(
            status: _pillStatus(receipt),
            label: _verificationLabel(strings, receipt),
          ),
          if (receipt.receiptNumber != null) ...[
            const SizedBox(height: SabSpacing.md),
            SectionCard(
              title: strings.receiptOfficialIdLabel,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        receipt.receiptNumber!,
                        style: SabTypography.monoCode.copyWith(
                          color: colors.textPrimary,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: SabSpacing.sm),
                _VerificationLine(receipt: receipt, strings: strings),
              ],
            ),
          ] else ...[
            const SizedBox(height: SabSpacing.md),
            _VerificationLine(receipt: receipt, strings: strings),
          ],
          if (receipt.unverifiedReason != null &&
              receipt.verificationStatus == ReceiptVerification.unverified) ...[
            const SizedBox(height: SabSpacing.sm),
            Text(
              receipt.unverifiedReason!,
              style: SabTypography.bodySmall.copyWith(
                color: colors.textSecondary,
              ),
            ),
          ],
          const SizedBox(height: SabSpacing.xl),
          SabButton(
            label: strings.shareReceipt,
            icon: SabIcons.send,
            expand: true,
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text(strings.receiptShareReady)),
              );
            },
          ),
          const SizedBox(height: SabSpacing.sm),
          SabButton(
            label: strings.exportReceipt,
            variant: SabButtonVariant.outline,
            expand: true,
            loading: documentBusy,
            onPressed: onExport,
          ),
          const SizedBox(height: SabSpacing.sm),
          SabButton(
            label: strings.raiseDispute,
            variant: SabButtonVariant.ghost,
            expand: true,
            loading: disputeBusy,
            onPressed: disputeBusy ? null : onDispute,
          ),
        ],
      ),
    );
  }

  static SabStatus _pillStatus(Receipt receipt) => switch (receipt.listStatus) {
    ReceiptListStatus.verified => SabStatus.verified,
    ReceiptListStatus.unverified => SabStatus.unverified,
    ReceiptListStatus.awaiting => SabStatus.awaitingReceipt,
  };

  static String _verificationLabel(SabStrings s, Receipt receipt) =>
      switch (receipt.listStatus) {
        ReceiptListStatus.verified => s.statusVerified,
        ReceiptListStatus.unverified => s.statusUnverified,
        ReceiptListStatus.awaiting => s.statusAwaitingReceipt,
      };

  static String _kindLabel(SabStrings s, ReceiptKind kind) => switch (kind) {
    ReceiptKind.officialEReceipt => s.kindOfficialReceipt,
    ReceiptKind.billerConfirmation => s.kindBillerConfirmation,
    ReceiptKind.token => s.kindToken,
  };
}

/// The verification line: states whether the identifier was confirmed against
/// its source, with the plain reason when it was not.
class _VerificationLine extends StatelessWidget {
  const _VerificationLine({required this.receipt, required this.strings});

  final Receipt receipt;
  final SabStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final (icon, label, tint) = switch (receipt.listStatus) {
      ReceiptListStatus.verified => (
        SabIcons.statusVerified,
        strings.receiptVerifiedLine,
        colors.success700,
      ),
      ReceiptListStatus.unverified => (
        SabIcons.statusUnverified,
        strings.receiptUnverifiedLine,
        colors.warning700,
      ),
      ReceiptListStatus.awaiting => (
        SabIcons.statusAwaitingReceipt,
        strings.receiptAwaitingLine,
        colors.info700,
      ),
    };
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SabIconView(icon, size: SabSizes.iconSm, color: tint),
        const SizedBox(width: SabSpacing.sm),
        Expanded(
          child: Text(
            label,
            style: SabTypography.bodySmall.copyWith(color: colors.textSecondary),
          ),
        ),
      ],
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.value});

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
              style: SabTypography.body.copyWith(color: colors.textPrimary),
            ),
          ),
        ],
      ),
    );
  }
}
