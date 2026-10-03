import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/error_state.dart';
import '../../components/offline_banner.dart';
import '../../components/sab_button.dart';
import '../../components/section_card.dart';
import '../../components/skeleton.dart';
import '../../components/status_pill.dart';
import '../../core/connectivity.dart';
import '../../core/money.dart';
import '../../data/providers.dart';
import '../../data/repositories.dart';
import '../../design_system/icons.dart';
import '../../design_system/sab_art.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import '../../models/payment_case.dart';
import '../receipts/receipts_controller.dart';

/// Screen 8: Case (`/cases/:caseId`). Shows the true state of a failed or
/// reversed payment and its firm expected timeline, drives a refund or
/// reconciliation, and reports progress. Covers pending, reconciling, refund
/// initiated, awaiting biller, escalated, resolved, and offline
/// (screens/08-case.md).
class CaseScreen extends ConsumerStatefulWidget {
  const CaseScreen({super.key, required this.caseId});

  final String caseId;

  @override
  ConsumerState<CaseScreen> createState() => _CaseScreenState();
}

class _CaseScreenState extends ConsumerState<CaseScreen> {
  bool _refundBusy = false;
  bool _disputeBusy = false;

  Future<void> _requestRefund(CaseDetail detail) async {
    final strings = ref.read(sabStringsProvider);
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _refundBusy = true);
    try {
      await ref.read(casesRepositoryProvider).refund(
        paymentId: detail.payment.paymentId,
        reason: 'Requested from the case screen',
        idempotencyKey: 'refund_${detail.payment.paymentId}',
      );
      ref.invalidate(caseDetailProvider(widget.caseId));
      messenger.showSnackBar(
        SnackBar(content: Text(strings.caseRefundSubmitted)),
      );
    } on DuplicateRefundException {
      messenger.showSnackBar(
        SnackBar(content: Text(strings.caseRefundBlocked)),
      );
    } on RefundNotAllowedException {
      messenger.showSnackBar(
        SnackBar(content: Text(strings.caseRefundBlocked)),
      );
    } catch (_) {
      messenger.showSnackBar(SnackBar(content: Text(strings.somethingWrong)));
    } finally {
      if (mounted) setState(() => _refundBusy = false);
    }
  }

  Future<void> _raiseDispute(CaseDetail detail) async {
    final strings = ref.read(sabStringsProvider);
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _disputeBusy = true);
    try {
      await ref.read(casesRepositoryProvider).dispute(
        caseId: detail.paymentCase.id,
        reason: 'Disputed from the case screen',
      );
      ref.invalidate(caseDetailProvider(widget.caseId));
      messenger.showSnackBar(
        SnackBar(content: Text(strings.caseRefundSubmitted)),
      );
    } on DuplicateDisputeException {
      messenger.showSnackBar(
        SnackBar(content: Text(strings.caseRefundBlocked)),
      );
    } catch (_) {
      messenger.showSnackBar(SnackBar(content: Text(strings.somethingWrong)));
    } finally {
      if (mounted) setState(() => _disputeBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = ref.watch(sabStringsProvider);
    final online = ref.watch(connectivityProvider);
    final async = ref.watch(caseDetailProvider(widget.caseId));

    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.pop()),
        title: Text(strings.caseTitle),
      ),
      body: Column(
        children: [
          if (!online) OfflineBanner(message: strings.caseOffline),
          Expanded(
            child: async.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(SabSpacing.md),
                child: SabSkeletonList(rows: 3),
              ),
              error: (_, _) => ErrorState(
                message: strings.caseNotFound,
                retryLabel: strings.retry,
                onRetry: () =>
                    ref.invalidate(caseDetailProvider(widget.caseId)),
              ),
              data: (detail) => _CaseBody(
                detail: detail,
                strings: strings,
                online: online,
                refundBusy: _refundBusy,
                disputeBusy: _disputeBusy,
                onRefund: () => _requestRefund(detail),
                onDispute: () => _raiseDispute(detail),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CaseBody extends ConsumerWidget {
  const _CaseBody({
    required this.detail,
    required this.strings,
    required this.online,
    required this.refundBusy,
    required this.disputeBusy,
    required this.onRefund,
    required this.onDispute,
  });

  final CaseDetail detail;
  final SabStrings strings;
  final bool online;
  final bool refundBusy;
  final bool disputeBusy;
  final VoidCallback onRefund;
  final VoidCallback onDispute;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final locale = ref.watch(localeProvider).code;
    final presentation = detail.presentation;
    final payment = detail.payment;
    final timeline = [...detail.timeline]
      ..sort((a, b) => b.occurredAt.compareTo(a.occurredAt));

    return SingleChildScrollView(
      padding: const EdgeInsets.all(SabSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // The status block: current state, last update, and the firm window.
          _StatusBlock(
            presentation: presentation,
            strings: strings,
            lastUpdated: detail.paymentCase.updatedAt,
          ),
          if (presentation == CasePresentation.reconciling) ...[
            const SizedBox(height: SabSpacing.md),
            Center(
              child: SabArt(
                artboard: SabArtboard.pending,
                size: SabSizes.artError,
                semanticLabel: strings.caseStateReconciling,
              ),
            ),
          ],
          const SizedBox(height: SabSpacing.md),
          // The confirmation summary: amount, payee, reference.
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
                  strings.amount,
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
                  style: SabTypography.h2.copyWith(color: colors.textPrimary),
                ),
                const SizedBox(height: SabSpacing.md),
                _CaseRow(label: strings.payee, value: payment.payee),
                _CaseRow(
                  label: strings.reference,
                  value: payment.paymentId,
                ),
                _CaseRow(
                  label: strings.caseReferenceLabel,
                  value: detail.paymentCase.id,
                ),
              ],
            ),
          ),
          if (payment.failureReason != null) ...[
            const SizedBox(height: SabSpacing.md),
            _ReasonNote(reason: payment.failureReason!),
          ],
          const SizedBox(height: SabSpacing.md),
          _CaseActions(
            presentation: presentation,
            strings: strings,
            online: online,
            refundBusy: refundBusy,
            disputeBusy: disputeBusy,
            onRefund: onRefund,
            onDispute: onDispute,
          ),
          const SizedBox(height: SabSpacing.xl),
          // The timeline: state changes, newest first.
          SectionCard(
            title: strings.caseTimelineTitle,
            children: [
              if (timeline.isEmpty)
                Text(
                  strings.loading,
                  style: SabTypography.bodySmall.copyWith(
                    color: colors.textSecondary,
                  ),
                )
              else
                for (var i = 0; i < timeline.length; i++)
                  _TimelineEntry(
                    event: timeline[i],
                    strings: strings,
                    isLast: i == timeline.length - 1,
                  ),
            ],
          ),
        ],
      ),
    );
  }
}

/// The status block: the current state pill, the last update time, and the
/// expected resolution window (screen 8, Layout).
class _StatusBlock extends ConsumerWidget {
  const _StatusBlock({
    required this.presentation,
    required this.strings,
    required this.lastUpdated,
  });

  final CasePresentation presentation;
  final SabStrings strings;
  final DateTime lastUpdated;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final locale = ref.watch(localeProvider).code;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        StatusPill(
          status: _pillFor(presentation),
          label: _labelFor(strings, presentation),
        ),
        const SizedBox(height: SabSpacing.sm),
        Text(
          SabStrings.fill(strings.caseLastUpdate, {
            'date': SabMoney.formatDate(lastUpdated, locale: locale),
          }),
          style: SabTypography.bodySmall.copyWith(color: colors.textSecondary),
        ),
        const SizedBox(height: SabSpacing.md),
        Row(
          children: [
            SabIconView(
              SabIcons.statusPending,
              size: SabSizes.iconSm,
              color: colors.textSecondary,
            ),
            const SizedBox(width: SabSpacing.sm),
            Expanded(
              child: Text(
                '${strings.caseExpectedWindow}: ${strings.caseExpectedWindowValue}',
                style: SabTypography.bodySmall.copyWith(
                  color: colors.textSecondary,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  static SabStatus _pillFor(CasePresentation p) => switch (p) {
    CasePresentation.pending => SabStatus.pending,
    CasePresentation.reconciling => SabStatus.pending,
    CasePresentation.refundInitiated => SabStatus.pending,
    CasePresentation.awaitingBiller => SabStatus.awaitingReceipt,
    CasePresentation.escalated => SabStatus.failed,
    CasePresentation.resolved => SabStatus.settled,
  };

  static String _labelFor(SabStrings s, CasePresentation p) => switch (p) {
    CasePresentation.pending => s.caseStatePending,
    CasePresentation.reconciling => s.caseStateReconciling,
    CasePresentation.refundInitiated => s.caseStateRefundInitiated,
    CasePresentation.awaitingBiller => s.caseStateAwaitingBiller,
    CasePresentation.escalated => s.caseStateEscalated,
    CasePresentation.resolved => s.caseStateResolved,
  };
}

/// The secondary and tertiary actions for the case. A status screen needs no
/// primary action; the refund path appears only where a case is reconciling or
/// awaiting the biller, and no action is offered offline.
class _CaseActions extends StatelessWidget {
  const _CaseActions({
    required this.presentation,
    required this.strings,
    required this.online,
    required this.refundBusy,
    required this.disputeBusy,
    required this.onRefund,
    required this.onDispute,
  });

  final CasePresentation presentation;
  final SabStrings strings;
  final bool online;
  final bool refundBusy;
  final bool disputeBusy;
  final VoidCallback onRefund;
  final VoidCallback onDispute;

  @override
  Widget build(BuildContext context) {
    final canRefund =
        online &&
        (presentation == CasePresentation.reconciling ||
            presentation == CasePresentation.awaitingBiller);
    final canDispute = online && presentation == CasePresentation.escalated;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (canRefund)
          SabButton(
            label: strings.caseStartRefund,
            icon: SabIcons.retry,
            expand: true,
            loading: refundBusy,
            onPressed: refundBusy ? null : onRefund,
          ),
        if (canDispute) ...[
          SabButton(
            label: strings.raiseDispute,
            expand: true,
            loading: disputeBusy,
            onPressed: disputeBusy ? null : onDispute,
          ),
          const SizedBox(height: SabSpacing.sm),
        ],
        SabButton(
          label: strings.caseContactSupport,
          variant: SabButtonVariant.outline,
          icon: SabIcons.help,
          expand: true,
          onPressed: online
              ? () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text(strings.caseSupportBody)),
                  );
                }
              : null,
        ),
        const SizedBox(height: SabSpacing.sm),
        SabButton(
          label: strings.caseViewReceipt,
          variant: SabButtonVariant.ghost,
          expand: true,
          onPressed: online
              ? () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text(strings.receiptShareReady)),
                  );
                }
              : null,
        ),
      ],
    );
  }
}

/// The plain reason a failure was recorded, stated above the actions.
class _ReasonNote extends StatelessWidget {
  const _ReasonNote({required this.reason});

  final String reason;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SabIconView(
          SabIcons.info,
          size: SabSizes.iconSm,
          color: colors.textSecondary,
        ),
        const SizedBox(width: SabSpacing.sm),
        Expanded(
          child: Text(
            reason,
            style: SabTypography.bodySmall.copyWith(
              color: colors.textSecondary,
            ),
          ),
        ),
      ],
    );
  }
}

/// One timeline entry: the state after the change, who caused it, when, and any
/// note. Newest first.
class _TimelineEntry extends ConsumerWidget {
  const _TimelineEntry({
    required this.event,
    required this.strings,
    required this.isLast,
  });

  final PaymentEvent event;
  final SabStrings strings;
  final bool isLast;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final locale = ref.watch(localeProvider).code;
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              Container(
                width: SabSpacing.sm,
                height: SabSpacing.sm,
                margin: const EdgeInsets.only(top: SabSpacing.xs),
                decoration: BoxDecoration(
                  color: colors.primary500,
                  shape: BoxShape.circle,
                ),
              ),
              if (!isLast)
                Expanded(
                  child: Container(width: 1, color: colors.border),
                ),
            ],
          ),
          const SizedBox(width: SabSpacing.md),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : SabSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _statusLabel(strings, event.status),
                    style: SabTypography.body.copyWith(
                      color: colors.textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: SabSpacing.xs),
                  Text(
                    '${_actorLabel(strings, event.actor)} · '
                    '${SabMoney.formatDate(event.occurredAt, locale: locale)}',
                    style: SabTypography.caption.copyWith(
                      color: colors.textSecondary,
                    ),
                  ),
                  if (event.detail != null) ...[
                    const SizedBox(height: SabSpacing.xs),
                    Text(
                      event.detail!,
                      style: SabTypography.bodySmall.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  static String _actorLabel(SabStrings s, String actor) => switch (actor) {
    'user' => s.caseActorUser,
    'rail' => s.caseActorRail,
    'provider' => s.caseActorProvider,
    _ => s.caseActorSystem,
  };

  static String _statusLabel(SabStrings s, String status) => switch (status) {
    'succeeded' => s.statusSettled,
    'failed' => s.statusFailed,
    'refunded' || 'reversed' => s.caseStateRefundInitiated,
    'authorized' => s.statusSettled,
    _ => s.statusPending,
  };
}

class _CaseRow extends StatelessWidget {
  const _CaseRow({required this.label, required this.value});

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
