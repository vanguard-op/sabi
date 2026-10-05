import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../components/error_state.dart';
import '../../components/sab_button.dart';
import '../../components/section_card.dart';
import '../../components/skeleton.dart';
import '../../components/status_pill.dart';
import '../../core/connectivity.dart';
import '../../core/money.dart';
import '../../design_system/icons.dart';
import '../../design_system/sab_art.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import '../../models/payment_case.dart';
import 'case_controller.dart';

/// The case recovery task rendered inline in the conversation (FEAT-009,
/// FEAT-011). It is the prewritten shell for the composed `Recovery` surface:
/// the agent-composed surface (or its fallback) sits above it, and this view
/// owns the client chrome — the status block, the timeline, and the refund,
/// dispute, and support actions.
///
/// It drives [caseControllerProvider], which holds the state machine, so no case
/// state is re-derived here: the view renders the controller's phase and
/// dispatches its actions. The same widget is the body of the Case screen, so
/// the conversation and the screen cannot drift apart. The C-026–C-029 calls are
/// the repository calls the controller makes; the view only shows the state and
/// dispatches the action.
class CaseTaskView extends ConsumerWidget {
  const CaseTaskView({super.key, required this.caseId});

  /// The case this view renders; the [caseControllerProvider] family key.
  final String caseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final state = ref.watch(caseControllerProvider(caseId));

    // Mirror connectivity into the controller so an action is refused offline
    // and a load retries when the connection returns.
    ref.listen<bool>(connectivityProvider, (_, next) {
      ref.read(caseControllerProvider(caseId).notifier).setOnline(next);
    });

    if (state.phase == CasePhase.loading && state.detail == null) {
      // The skeleton is a scrollable list; bound it so the view can sit inside
      // either the screen's scroll or the conversation's list without nesting
      // an unbounded viewport.
      return const SizedBox(
        height: 360,
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: SabSpacing.md),
          child: SabSkeletonList(rows: 3),
        ),
      );
    }

    if (state.phase == CasePhase.error && state.detail == null) {
      return ErrorState(
        message: strings.caseNotFound,
        retryLabel: strings.retry,
        onRetry: () => ref.read(caseControllerProvider(caseId).notifier).load(),
      );
    }

    final detail = state.detail;
    if (detail == null) return const SizedBox.shrink();

    return _CaseBody(caseId: caseId, state: state, detail: detail);
  }
}

class _CaseBody extends ConsumerWidget {
  const _CaseBody({
    required this.caseId,
    required this.state,
    required this.detail,
  });

  final String caseId;
  final CaseState state;
  final CaseDetail detail;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    final locale = ref.watch(localeProvider).code;
    final presentation = state.presentation;
    final payment = detail.payment;
    final timeline = [...detail.timeline]
      ..sort((a, b) => b.occurredAt.compareTo(a.occurredAt));

    return Column(
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
              _CaseRow(label: strings.reference, value: payment.paymentId),
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
        _CaseActions(caseId: caseId, state: state, strings: strings),
        if (state.notice != null) ...[
          const SizedBox(height: SabSpacing.md),
          _OutcomeNotice(notice: state.notice!, strings: strings),
        ],
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
/// primary action; the refund path appears where a case is reconciling or
/// awaiting the biller, the dispute path on an escalated case, and no action is
/// offered offline. Both actions dispatch the controller, which holds the
/// C-028/C-029 calls.
class _CaseActions extends ConsumerWidget {
  const _CaseActions({
    required this.caseId,
    required this.state,
    required this.strings,
  });

  final String caseId;
  final CaseState state;
  final SabStrings strings;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(caseControllerProvider(caseId).notifier);
    final refunding = state.phase == CasePhase.refunding;
    final disputing = state.phase == CasePhase.disputing;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (state.canRefund)
          SabButton(
            label: strings.caseStartRefund,
            icon: SabIcons.retry,
            expand: true,
            loading: refunding,
            onPressed: refunding ? null : controller.refund,
          ),
        if (state.canDispute) ...[
          SabButton(
            label: strings.raiseDispute,
            expand: true,
            loading: disputing,
            onPressed: disputing ? null : controller.dispute,
          ),
          const SizedBox(height: SabSpacing.sm),
        ],
        SabButton(
          label: strings.caseContactSupport,
          variant: SabButtonVariant.outline,
          icon: SabIcons.help,
          expand: true,
          onPressed: state.online ? () => _showSupport(context) : null,
        ),
        const SizedBox(height: SabSpacing.sm),
        SabButton(
          label: strings.caseViewReceipt,
          variant: SabButtonVariant.ghost,
          expand: true,
          onPressed: state.online
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

  void _showSupport(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(strings.caseContactSupport),
        content: Text(strings.caseSupportBody),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(strings.close),
          ),
        ],
      ),
    );
  }
}

/// The outcome of the last refund or dispute, stated inline so the user sees
/// whether it went through. The colour pairs with an icon and a text label, so
/// colour is never the only signal (branding.md, "Accessibility").
class _OutcomeNotice extends StatelessWidget {
  const _OutcomeNotice({required this.notice, required this.strings});

  final CaseNotice notice;
  final SabStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final (icon, tint, text) = switch (notice) {
      CaseNotice.refundSubmitted => (
        SabIcons.statusSettled,
        colors.success700,
        strings.caseRefundSubmitted,
      ),
      CaseNotice.refundBlocked => (
        SabIcons.info,
        colors.info700,
        strings.caseRefundBlocked,
      ),
      CaseNotice.disputeSubmitted => (
        SabIcons.statusSettled,
        colors.success700,
        strings.caseDisputeSubmitted,
      ),
      CaseNotice.disputeBlocked => (
        SabIcons.info,
        colors.info700,
        strings.caseDisputeBlocked,
      ),
      CaseNotice.actionFailed => (
        SabIcons.error,
        colors.error700,
        strings.somethingWrong,
      ),
    };
    return Semantics(
      liveRegion: true,
      container: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(SabSpacing.md),
        decoration: BoxDecoration(
          color: colors.surfaceSecondary,
          borderRadius: BorderRadius.circular(SabRadii.md),
          border: Border.all(color: colors.border),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SabIconView(icon, size: SabSizes.iconSm, color: tint),
            const SizedBox(width: SabSpacing.sm),
            Expanded(
              child: Text(
                text,
                style: SabTypography.bodySmall.copyWith(
                  color: colors.textSecondary,
                ),
              ),
            ),
          ],
        ),
      ),
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
                Expanded(child: Container(width: 1, color: colors.border)),
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
