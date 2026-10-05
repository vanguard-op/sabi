import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../a2ui/a2ui_surface.dart';
import '../../a2ui/sabi_catalog.dart';
import '../../components/sab_button.dart';
import '../../components/sab_text_field.dart';
import '../../components/skeleton.dart';
import '../../components/status_pill.dart';
import '../../components/success_toast.dart';
import '../../core/connectivity.dart';
import '../../design_system/icons.dart';
import '../../design_system/sab_art.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import 'models/payment.dart';
import 'payment_controller.dart';
import 'payment_strings.dart';

/// The payment task rendered inline in the conversation (FEAT-005/006/007,
/// FEAT-011). It is the prewritten form for the composed confirmation surface:
/// the agent-composed summary (or its fallback) sits above, and this view owns
/// the client chrome — the authorise action, the flow panels, and every state
/// the payment moves through.
///
/// It drives [paymentControllerProvider], which holds the state machine, so no
/// payment state is re-derived here: the view renders the controller's phase and
/// dispatches its actions. The confirmation gate is unchanged: the authorise
/// action is the explicit confirmation, and no payment is submitted without it.
class PaymentTaskView extends ConsumerWidget {
  const PaymentTaskView({
    super.key,
    required this.serviceId,
    required this.summaryFallback,
    this.surface,
    this.onValidationFailed,
    this.onOpenVerification,
    this.onOpenReceipt,
  });

  final String serviceId;

  /// The prewritten confirmation summary, used when the composed surface is
  /// refused or the SDK cannot render it.
  final WidgetBuilder summaryFallback;

  /// The gated A2UI stream for the confirmation, or null for the fallback.
  final A2uiSurfaceStream? surface;
  final void Function(Map<String, Object?> error)? onValidationFailed;

  /// Opens the Identity screen for a payment held pending verification.
  final VoidCallback? onOpenVerification;

  /// Opens a stored receipt for a settled bill.
  final ValueChanged<String>? onOpenReceipt;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final payment = ref.watch(paymentStringsProvider);
    final online = ref.watch(connectivityProvider);
    final state = ref.watch(paymentControllerProvider(serviceId));

    if (state.phase == PaymentPhase.resolving) {
      return const _TaskSkeleton();
    }

    // A settled federal payment shows its official e-receipt in place of the
    // summary, marked verified or unverified against the source (FEAT-006).
    if (state.phase == PaymentPhase.settled && state.isFederal) {
      return _FederalReceiptView(state: state, payment: payment);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        A2uiSurfaceView(
          stream: surface,
          onValidationFailed: onValidationFailed,
          fallback: summaryFallback,
        ),
        if (state.phase == PaymentPhase.amountEntry) ...[
          const SizedBox(height: SabSpacing.md),
          SabAmountEntryField(
            strings: strings,
            minimum: state.billValidation?.range?.minimum,
            maximum: state.billValidation?.range?.maximum,
            onSubmit: (minor) => ref
                .read(paymentControllerProvider(serviceId).notifier)
                .setAmount(minor),
          ),
        ] else if (state.isVariable && state.effectiveAmount == null) ...[
          const SizedBox(height: SabSpacing.sm),
          Text(
            payment.amountConfirmedAtPayment,
            style: SabTypography.bodySmall.copyWith(
              color: SabColorTokens.of(context).textSecondary,
            ),
          ),
        ],
        const SizedBox(height: SabSpacing.lg),
        if (state.isFederal)
          _FederalPanel(
            state: state,
            payment: payment,
            serviceId: serviceId,
          ),
        if (state.isBill)
          _BillPanel(state: state, payment: payment, serviceId: serviceId),
        if (state.isBill &&
            state.phase == PaymentPhase.settled &&
            state.billToken?.token != null)
          _BillTokenView(token: state.billToken!, payment: payment),
        if (state.phase == PaymentPhase.collectionChanged)
          _CollectionChangedNotice(serviceId: serviceId),
        _StateNotice(state: state, payment: payment, strings: strings),
        ..._actions(ref, state, payment, strings, online),
      ],
    );
  }

  List<Widget> _actions(
    WidgetRef ref,
    PaymentConfirmationState state,
    PaymentStrings payment,
    SabStrings strings,
    bool online,
  ) {
    final controller = ref.read(paymentControllerProvider(serviceId).notifier);
    final actions = <Widget>[];
    void add(Widget widget) {
      if (actions.isNotEmpty) actions.add(const SizedBox(height: SabSpacing.sm));
      actions.add(widget);
    }

    switch (state.phase) {
      case PaymentPhase.settled:
        final receiptId = state.billToken?.receiptId;
        if (state.isBill && receiptId != null && onOpenReceipt != null) {
          add(
            SabButton(
              label: payment.viewReceipt,
              expand: true,
              onPressed: () => onOpenReceipt!(receiptId),
            ),
          );
        }
      case PaymentPhase.reconciling:
      case PaymentPhase.awaitingReceipt:
      case PaymentPhase.awaitingToken:
        add(
          SabButton(
            label: strings.retry,
            variant: SabButtonVariant.secondary,
            expand: true,
            onPressed: controller.retryProof,
          ),
        );
      case PaymentPhase.heldForKyc:
        if (onOpenVerification != null) {
          add(
            SabButton(
              label: payment.verifyNow,
              expand: true,
              onPressed: onOpenVerification,
            ),
          );
        }
      case PaymentPhase.collectionChanged:
        add(
          SabButton(
            label: payment.reResolve,
            expand: true,
            onPressed: controller.reResolve,
          ),
        );
      case PaymentPhase.refunding:
        add(
          SabButton(
            label: payment.refundStarting,
            expand: true,
            loading: true,
            onPressed: null,
          ),
        );
      case PaymentPhase.failure:
        if (state.refundAvailable && state.paymentId != null) {
          add(
            SabButton(
              label: payment.startRefund,
              expand: true,
              onPressed: controller.requestRefund,
            ),
          );
        }
      case PaymentPhase.secondConfirmation:
        add(
          SabButton(
            label: payment.confirmAndPay,
            expand: true,
            onPressed: controller.confirmSecondTime,
          ),
        );
        add(
          SabButton(
            label: payment.cancel,
            variant: SabButtonVariant.ghost,
            expand: true,
            onPressed: controller.declineSecondTime,
          ),
        );
      case PaymentPhase.authorising:
        add(
          SabButton(
            label: payment.authorising,
            expand: true,
            loading: true,
            onPressed: null,
          ),
        );
      case PaymentPhase.ready:
        // The authorise action is the explicit confirmation: the mandate is
        // signed for the amount and payee the user was shown.
        add(
          SabButton(
            label: payment.authorisePayment,
            expand: true,
            onPressed: online ? controller.submit : null,
          ),
        );
      case PaymentPhase.resolving:
      case PaymentPhase.amountEntry:
      case PaymentPhase.referenceRequired:
      case PaymentPhase.recipientRequired:
      case PaymentPhase.refundRequested:
      case PaymentPhase.error:
      case PaymentPhase.offline:
        // A required field, a notice, or the offline banner carries the next
        // step; there is no authorise action to offer.
        break;
    }
    return actions;
  }
}

/// The first-load skeleton for a resolving obligation, sized for the
/// conversation rather than a full screen.
class _TaskSkeleton extends StatelessWidget {
  const _TaskSkeleton();

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Semantics(
      label: 'Loading',
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(SabSpacing.md),
        decoration: BoxDecoration(
          color: colors.surfaceSecondary,
          borderRadius: BorderRadius.circular(SabRadii.md),
          border: Border.all(color: colors.border),
        ),
        child: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SabSkeleton(width: 160, height: SabSpacing.md),
            SizedBox(height: SabSpacing.sm),
            SabSkeleton(width: 100, height: SabSpacing.sm),
          ],
        ),
      ),
    );
  }
}

/// The federal sub-panel: payer-reference entry and the switched-collection
/// notice (FEAT-006, C-030).
class _FederalPanel extends ConsumerStatefulWidget {
  const _FederalPanel({
    required this.state,
    required this.payment,
    required this.serviceId,
  });

  final PaymentConfirmationState state;
  final PaymentStrings payment;
  final String serviceId;

  @override
  ConsumerState<_FederalPanel> createState() => _FederalPanelState();
}

class _FederalPanelState extends ConsumerState<_FederalPanel> {
  final _reference = TextEditingController();

  @override
  void dispose() {
    _reference.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final state = widget.state;
    final payment = widget.payment;
    final prepare = state.federalPrepare;
    if (prepare == null) return const SizedBox.shrink();
    final referenceMissing =
        prepare.requiresReference && (state.reference ?? '').isEmpty;

    if (!prepare.requiresReference && prepare.instructions == null) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.only(bottom: SabSpacing.lg),
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: referenceMissing ? colors.warning100 : colors.surfaceSecondary,
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SabIconView(
                referenceMissing ? SabIcons.info : SabIcons.statusVerified,
                size: SabSizes.iconSm,
                color: referenceMissing
                    ? colors.warning900
                    : colors.textSecondary,
              ),
              const SizedBox(width: SabSpacing.sm),
              Expanded(
                child: Text(
                  referenceMissing
                      ? payment.federalReferenceNeeded
                      : payment.federalTitle,
                  style: SabTypography.body.copyWith(
                    color: referenceMissing
                        ? colors.warning900
                        : colors.textPrimary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          if (prepare.instructions != null) ...[
            const SizedBox(height: SabSpacing.xs),
            Text(
              prepare.instructions!,
              style: SabTypography.bodySmall.copyWith(
                color: referenceMissing
                    ? colors.warning900
                    : colors.textSecondary,
              ),
            ),
          ],
          if (referenceMissing) ...[
            const SizedBox(height: SabSpacing.md),
            SabTextField(
              label: payment.federalReferenceLabel,
              hint: payment.federalReferenceHint,
              controller: _reference,
              textInputAction: TextInputAction.done,
              onSubmitted: (value) => ref
                  .read(paymentControllerProvider(widget.serviceId).notifier)
                  .setReference(value),
            ),
          ],
        ],
      ),
    );
  }
}

/// The bill sub-panel: recipient entry and its validation outcome (FEAT-007,
/// C-033).
class _BillPanel extends ConsumerStatefulWidget {
  const _BillPanel({
    required this.state,
    required this.payment,
    required this.serviceId,
  });

  final PaymentConfirmationState state;
  final PaymentStrings payment;
  final String serviceId;

  @override
  ConsumerState<_BillPanel> createState() => _BillPanelState();
}

class _BillPanelState extends ConsumerState<_BillPanel> {
  final _recipient = TextEditingController();

  @override
  void dispose() {
    _recipient.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final state = widget.state;
    final payment = widget.payment;
    final validation = state.billValidation;
    // The resolved service names the identifier it expects: an electricity
    // biller wants a meter number, airtime a phone number, water an account.
    final recipient = _recipientCopy(state, payment);
    return Container(
      margin: const EdgeInsets.only(bottom: SabSpacing.lg),
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.surfaceSecondary,
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            payment.billTitle,
            style: SabTypography.body.copyWith(
              color: colors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: SabSpacing.md),
          if (state.phase == PaymentPhase.recipientRequired)
            SabTextField(
              label: recipient.label,
              hint: recipient.hint,
              controller: _recipient,
              textInputAction: TextInputAction.done,
              onSubmitted: (value) => ref
                  .read(paymentControllerProvider(widget.serviceId).notifier)
                  .setRecipient(value),
            )
          else
            _ValueRow(label: recipient.label, value: state.recipient ?? ''),
          if (state.phase == PaymentPhase.failure &&
              validation != null &&
              !validation.valid &&
              validation.reason != null) ...[
            const SizedBox(height: SabSpacing.sm),
            Text(
              validation.reason!,
              style: SabTypography.bodySmall.copyWith(color: colors.error500),
            ),
          ],
        ],
      ),
    );
  }
}

/// The label and hint for a bill's recipient field, derived from the resolved
/// service so every biller gets the identifier it actually expects (FEAT-007).
({String label, String hint}) _recipientCopy(
  PaymentConfirmationState state,
  PaymentStrings payment,
) {
  final service = state.obligation.service;
  return switch (BillRecipientKind.forService(
    name: service.name,
    category: service.category,
  )) {
    BillRecipientKind.meter => (
      label: payment.meterLabel,
      hint: payment.meterHint,
    ),
    BillRecipientKind.phone => (
      label: payment.phoneLabel,
      hint: payment.phoneHint,
    ),
    BillRecipientKind.account => (
      label: payment.accountLabel,
      hint: payment.accountHint,
    ),
    BillRecipientKind.generic => (
      label: payment.recipientLabel,
      hint: payment.recipientHint,
    ),
  };
}

/// The returned prepaid token, shown in monospace so it can be read and copied
/// character by character, and stored with the receipt (FEAT-007).
class _BillTokenView extends StatelessWidget {
  const _BillTokenView({required this.token, required this.payment});

  final BillToken token;
  final PaymentStrings payment;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final value = token.token ?? '';
    return Container(
      margin: const EdgeInsets.only(bottom: SabSpacing.lg),
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.success100,
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            payment.tokenLabel,
            style: SabTypography.caption.copyWith(color: colors.success900),
          ),
          const SizedBox(height: SabSpacing.xs),
          Row(
            children: [
              Expanded(
                child: Text(
                  value,
                  style: SabTypography.monoCode.copyWith(
                    color: colors.success900,
                  ),
                ),
              ),
              SabButton(
                label: payment.copyToken,
                variant: SabButtonVariant.ghost,
                icon: SabIcons.copy,
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: value));
                  if (context.mounted) {
                    showSabSuccessToast(context, payment.tokenCopied);
                  }
                },
              ),
            ],
          ),
          const SizedBox(height: SabSpacing.xs),
          Text(
            payment.tokenStored,
            style: SabTypography.bodySmall.copyWith(color: colors.success900),
          ),
        ],
      ),
    );
  }
}

/// A compact label/value line: the label on the left and the value right
/// aligned. The value is allowed to shrink and ellipsize instead of reserving a
/// fixed label column and stretching the value across the remaining width.
class _ValueRow extends StatelessWidget {
  const _ValueRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Flexible(
          child: Text(
            label,
            style: SabTypography.bodySmall.copyWith(
              color: colors.textSecondary,
            ),
          ),
        ),
        const SizedBox(width: SabSpacing.md),
        Flexible(
          child: Text(
            value,
            textAlign: TextAlign.end,
            overflow: TextOverflow.ellipsis,
            style: SabTypography.mono.copyWith(color: colors.textPrimary),
          ),
        ),
      ],
    );
  }
}

/// The inline notice for the non-default states: failure, reconciling, held for
/// KYC, awaiting proof, second confirmation, and error. Each pairs a semantic
/// colour with an icon and a text label (branding.md, "Accessibility").
class _StateNotice extends StatelessWidget {
  const _StateNotice({
    required this.state,
    required this.payment,
    required this.strings,
  });

  final PaymentConfirmationState state;
  final PaymentStrings payment;
  final SabStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    // A settled bill renders its token view instead; the success notice would
    // only repeat it.
    if (state.phase == PaymentPhase.settled && state.isBill) {
      return const SizedBox.shrink();
    }
    final (icon, colour, title, body, pill) = switch (state.phase) {
      PaymentPhase.authorising => (
        SabIcons.statusPending,
        colors.warning500,
        payment.authorising,
        null,
        SabStatus.pending,
      ),
      PaymentPhase.settled => (
        SabIcons.statusSettled,
        colors.success500,
        payment.successTitle,
        payment.successBody,
        SabStatus.settled,
      ),
      PaymentPhase.heldForKyc => (
        SabIcons.info,
        colors.info500,
        payment.heldForKycTitle,
        payment.heldForKycBody,
        null,
      ),
      PaymentPhase.secondConfirmation => (
        SabIcons.info,
        colors.info500,
        payment.secondConfirmationTitle,
        payment.secondConfirmationBody,
        null,
      ),
      PaymentPhase.failure => (
        SabIcons.statusFailed,
        colors.error500,
        state.refundAvailable
            ? payment.billTokenFailedTitle
            : payment.failureTitle,
        state.failure ?? strings.somethingWrong,
        SabStatus.failed,
      ),
      PaymentPhase.reconciling => (
        SabIcons.statusPending,
        colors.warning500,
        payment.reconcilingTitle,
        payment.reconcilingBody,
        SabStatus.pending,
      ),
      PaymentPhase.refunding => (
        SabIcons.statusPending,
        colors.warning500,
        payment.refundStarting,
        null,
        SabStatus.pending,
      ),
      PaymentPhase.refundRequested => (
        SabIcons.statusPending,
        colors.info500,
        payment.refundStartedTitle,
        payment.refundStartedBody,
        SabStatus.pending,
      ),
      PaymentPhase.awaitingReceipt => (
        SabIcons.statusAwaitingReceipt,
        colors.info500,
        payment.awaitingReceiptTitle,
        payment.awaitingReceiptBody,
        SabStatus.awaitingReceipt,
      ),
      PaymentPhase.awaitingToken => (
        SabIcons.statusAwaitingReceipt,
        colors.info500,
        payment.awaitingTokenTitle,
        payment.awaitingTokenBody,
        SabStatus.awaitingReceipt,
      ),
      PaymentPhase.error => (
        SabIcons.error,
        colors.error500,
        strings.somethingWrong,
        state.failure ?? strings.errorGeneric,
        null,
      ),
      PaymentPhase.offline => (
        SabIcons.offline,
        colors.warning500,
        strings.offlineNoPayment,
        null,
        null,
      ),
      _ => (null, null, null, null, null),
    };
    if (title == null) return const SizedBox.shrink();

    return Semantics(
      liveRegion: true,
      container: true,
      child: Container(
        padding: const EdgeInsets.all(SabSpacing.md),
        decoration: BoxDecoration(
          color: colors.surfaceSecondary,
          borderRadius: BorderRadius.circular(SabRadii.md),
          border: Border.all(color: colors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SabIconView(icon!, size: SabSizes.iconMd, color: colour!),
                const SizedBox(width: SabSpacing.sm),
                Expanded(
                  child: Text(
                    title,
                    style: SabTypography.body.copyWith(
                      color: colors.textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            if (body != null) ...[
              const SizedBox(height: SabSpacing.xs),
              Text(
                body,
                style: SabTypography.bodySmall.copyWith(
                  color: colors.textSecondary,
                ),
              ),
            ],
            if (pill != null) ...[
              const SizedBox(height: SabSpacing.sm),
              StatusPill(status: pill),
            ],
          ],
        ),
      ),
    );
  }
}

/// The settled federal state: the official FTeR, marked verified or unverified
/// against the source (FEAT-006, C-031).
class _FederalReceiptView extends StatelessWidget {
  const _FederalReceiptView({required this.state, required this.payment});

  final PaymentConfirmationState state;
  final PaymentStrings payment;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final receipt = state.federalReceipt;
    final verified = receipt?.verificationStatus == 'verified';
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
          const SabArt(
            artboard: SabArtboard.success,
            size: SabSizes.artEmptyState,
            semanticLabel: 'Payment settled',
          ),
          const SizedBox(height: SabSpacing.lg),
          Text(
            payment.successTitle,
            style: SabTypography.h3.copyWith(color: colors.textPrimary),
          ),
          const SizedBox(height: SabSpacing.sm),
          Text(
            payment.successBody,
            style: SabTypography.bodySmall.copyWith(
              color: colors.textSecondary,
            ),
          ),
          const SizedBox(height: SabSpacing.lg),
          _ValueRow(
            label: payment.officialReceipt,
            value: receipt?.receiptNumber ?? '',
          ),
          const SizedBox(height: SabSpacing.sm),
          StatusPill(
            status: verified ? SabStatus.verified : SabStatus.unverified,
            label: verified ? payment.receiptVerified : payment.receiptUnverified,
          ),
        ],
      ),
    );
  }
}

/// A federal notice for a switched collection account, with the explicit
/// re-resolve action (FEAT-006, alternate G).
class _CollectionChangedNotice extends ConsumerWidget {
  const _CollectionChangedNotice({required this.serviceId});

  final String serviceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final payment = ref.watch(paymentStringsProvider);
    final colors = SabColorTokens.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: SabSpacing.md),
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.warning100,
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            payment.collectionChangedTitle,
            style: SabTypography.body.copyWith(
              color: colors.warning900,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: SabSpacing.xs),
          Text(
            payment.collectionChangedBody,
            style: SabTypography.bodySmall.copyWith(color: colors.warning900),
          ),
          const SizedBox(height: SabSpacing.sm),
          SabButton(
            label: payment.reResolve,
            variant: SabButtonVariant.outline,
            onPressed: () => ref
                .read(paymentControllerProvider(serviceId).notifier)
                .reResolve(),
          ),
        ],
      ),
    );
  }
}
