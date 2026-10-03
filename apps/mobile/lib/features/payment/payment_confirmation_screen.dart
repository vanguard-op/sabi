import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/amount_entry_sheet.dart';
import '../../components/confirmation_summary.dart';
import '../../components/offline_banner.dart';
import '../../components/reauth_dialog.dart';
import '../../components/sab_button.dart';
import '../../components/sab_text_field.dart';
import '../../components/skeleton.dart';
import '../../components/status_pill.dart';
import '../../components/success_toast.dart';
import '../../core/connectivity.dart';
import '../../core/money.dart';
import '../../core/reauth.dart';
import '../../data/providers.dart';
import '../../design_system/icons.dart';
import '../../design_system/sab_art.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import 'models/payment.dart';
import 'payment_controller.dart';
import 'payment_strings.dart';

/// Screen 4: Payment Confirmation (`/pay/:serviceId`).
///
/// Shows the amount, payee, charges, and reference for a resolved obligation
/// and takes explicit authorisation. The surface is flow-aware: a federal
/// collection resolves its collection facts first (FEAT-006) and a bill
/// validates its recipient (FEAT-007), while the common authorise-and-execute
/// path carries every payment (FEAT-005).
///
/// Every state from screens/04 renders here: default, amount entry, authorising,
/// held for KYC, failure, reconciling, awaiting proof, settled, and offline.
class PaymentConfirmationScreen extends ConsumerStatefulWidget {
  const PaymentConfirmationScreen({super.key, required this.serviceId});

  final String serviceId;

  @override
  ConsumerState<PaymentConfirmationScreen> createState() =>
      _PaymentConfirmationScreenState();
}

class _PaymentConfirmationScreenState
    extends ConsumerState<PaymentConfirmationScreen> {
  final _reference = TextEditingController();
  final _recipient = TextEditingController();

  @override
  void initState() {
    super.initState();
    // Resolve after the first frame: the skeleton is already on screen and the
    // controller's state is initialised, so the federal prepare or bill
    // validation lands without blocking the first paint.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        ref
            .read(paymentControllerProvider(widget.serviceId).notifier)
            .resolve();
      }
    });
  }

  @override
  void dispose() {
    _reference.dispose();
    _recipient.dispose();
    super.dispose();
  }

  PaymentController get _controller =>
      ref.read(paymentControllerProvider(widget.serviceId).notifier);

  PaymentConfirmationState get _state =>
      ref.read(paymentControllerProvider(widget.serviceId));

  Future<void> _openAmountSheet() async {
    final state = _state;
    final range = state.billValidation?.range;
    final entered = await showSabAmountEntrySheet(
      context,
      minMinor: range?.minimum,
      maxMinor: range?.maximum,
      currency: state.obligation.currency,
    );
    if (entered != null && mounted) await _controller.setAmount(entered);
  }

  Future<void> _authorise() async {
    await _controller.submit();
  }

  Future<void> _confirmSecondTime() async {
    final confirmed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => _SecondConfirmationDialog(
        amount: _state.effectiveAmount,
        currency: _state.obligation.currency,
        payee: _state.obligation.payee,
      ),
    );
    if (confirmed == true) {
      await _controller.confirmSecondTime();
    }
  }

  Future<void> _showReauth() async {
    final ok = await showSabReauthDialog(
      context,
      onReauth: () async {
        try {
          await ref.read(authRepositoryProvider).signInWithPasskey();
          return true;
        } catch (_) {
          return false;
        }
      },
    );
    if (!mounted) return;
    ref.read(reauthProvider.notifier).resolve();
    if (ok) ref.read(sessionProvider).signIn();
  }

  @override
  Widget build(BuildContext context) {
    final strings = ref.watch(sabStringsProvider);
    final payment = ref.watch(paymentStringsProvider);
    final online = ref.watch(connectivityProvider);
    final state = ref.watch(paymentControllerProvider(widget.serviceId));

    // The controller also owns the offline gate; a dropped connection while the
    // screen is open flips the surface without losing the entered data.
    ref.listen<bool>(connectivityProvider, (_, next) {
      if (!next) {
        _controller.resolve();
      }
    });
    // A second confirmation is a blocking overlay it opens once.
    ref.listen<PaymentPhase>(
      paymentControllerProvider(widget.serviceId).select((s) => s.phase),
      (previous, next) {
        if (next == PaymentPhase.secondConfirmation) _confirmSecondTime();
      },
    );
    ref.listen<bool>(reauthProvider, (previous, next) {
      if (next) _showReauth();
    });

    final title = state.obligation.service.collectingBody;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.pop()),
        title: Text(title, overflow: TextOverflow.ellipsis),
      ),
      body: Column(
        children: [
          if (!online) OfflineBanner(message: payment.offlineNoAuthorisation),
          Expanded(child: _buildBody(strings, payment, state)),
        ],
      ),
      bottomNavigationBar: _buildActionBar(strings, payment, state, online),
    );
  }

  Widget _buildBody(
    SabStrings strings,
    PaymentStrings payment,
    PaymentConfirmationState state,
  ) {
    if (state.phase == PaymentPhase.resolving) {
      return const Padding(
        padding: EdgeInsets.all(SabSpacing.md),
        child: SabSkeletonList(rows: 3),
      );
    }
    if (state.phase == PaymentPhase.settled && state.isFederal) {
      return _FederalReceiptView(state: state, payment: payment);
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(SabSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ConfirmationSummary(
            amount: state.effectiveAmount ?? 0,
            currency: state.obligation.currency,
            payee: state.obligation.payee,
            charges: state.obligation.charges,
            reference: state.reference ?? state.obligation.reference,
          ),
          if (state.isVariable && state.effectiveAmount == null) ...[
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
              referenceController: _reference,
              serviceId: widget.serviceId,
            ),
          if (state.isBill)
            _BillPanel(
              state: state,
              payment: payment,
              recipientController: _recipient,
              serviceId: widget.serviceId,
            ),
          if (state.isBill &&
              state.phase == PaymentPhase.settled &&
              state.billToken?.token != null)
            _BillTokenView(token: state.billToken!, payment: payment),
          if (state.phase == PaymentPhase.collectionChanged)
            _CollectionChangedNotice(serviceId: widget.serviceId),
          _StateNotice(state: state, payment: payment, strings: strings),
        ],
      ),
    );
  }

  Widget? _buildActionBar(
    SabStrings strings,
    PaymentStrings payment,
    PaymentConfirmationState state,
    bool online,
  ) {
    // No pinned action while the obligation is still resolving.
    if (state.phase == PaymentPhase.resolving) return null;

    final colors = SabColorTokens.of(context);
    final actions = <Widget>[];

    if (state.phase == PaymentPhase.settled) {
      final receiptId = state.billToken?.receiptId;
      final hasReceipt = receiptId != null && state.isBill;
      actions.add(
        SabButton(
          label: hasReceipt ? payment.viewReceipt : payment.doneLabel,
          expand: true,
          onPressed: () {
            if (hasReceipt) {
              context.push('/receipts/$receiptId');
              return;
            }
            context.pop();
          },
        ),
      );
    } else if (state.phase == PaymentPhase.reconciling) {
      actions.add(
        SabButton(
          label: strings.retry,
          variant: SabButtonVariant.secondary,
          expand: true,
          onPressed: () => _controller.retryProof(),
        ),
      );
    } else if (state.phase == PaymentPhase.heldForKyc) {
      actions.add(
        SabButton(
          label: payment.verifyNow,
          expand: true,
          onPressed: () => context.push('/account/verify?from=payment'),
        ),
      );
      actions.add(const SizedBox(height: SabSpacing.sm));
      actions.add(
        SabButton(
          label: strings.back,
          variant: SabButtonVariant.ghost,
          expand: true,
          onPressed: () => context.pop(),
        ),
      );
    } else if (state.phase == PaymentPhase.collectionChanged) {
      // The obligation is stale: re-resolve rather than authorise against the
      // old collection account (FEAT-006, alternate G).
      actions.add(
        SabButton(
          label: payment.reResolve,
          expand: true,
          onPressed: () => _controller.reResolve(),
        ),
      );
    } else {
      // The primary action varies with the flow's current requirement.
      final needsAmount = state.effectiveAmount == null;
      final needsReference =
          state.isFederal &&
          state.federalPrepare?.requiresReference == true &&
          (state.reference ?? '').isEmpty;
      final needsRecipient = state.isBill && (state.recipient ?? '').isEmpty;

      actions.add(
        SabButton(
          label: needsAmount
              ? payment.changeAmount
              : needsReference
              ? payment.continueLabel
              : needsRecipient
              ? payment.continueLabel
              : payment.authorisePayment,
          expand: true,
          loading: state.phase == PaymentPhase.authorising,
          onPressed: state.phase == PaymentPhase.authorising || !online
              ? null
              : needsAmount
              ? _openAmountSheet
              : _authorise,
        ),
      );
      if (state.effectiveAmount != null && state.obligation.isVariable) {
        actions.add(const SizedBox(height: SabSpacing.xs));
        actions.add(
          SabButton(
            label: payment.changeAmount,
            variant: SabButtonVariant.ghost,
            expand: true,
            onPressed: state.isLocked ? null : _openAmountSheet,
          ),
        );
      }
    }

    return Container(
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border(top: BorderSide(color: colors.border)),
      ),
      padding: const EdgeInsets.fromLTRB(
        SabSpacing.md,
        SabSpacing.md,
        SabSpacing.md,
        SabSpacing.sm,
      ),
      child: SafeArea(
        top: false,
        child: Column(mainAxisSize: MainAxisSize.min, children: actions),
      ),
    );
  }
}

/// A blocking dialog for an amount above the user's set limit (FEAT-005).
class _SecondConfirmationDialog extends ConsumerWidget {
  const _SecondConfirmationDialog({
    required this.amount,
    required this.currency,
    required this.payee,
  });

  final int? amount;
  final String currency;
  final String payee;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final payment = ref.watch(paymentStringsProvider);
    final locale = ref.watch(localeProvider).code;
    return AlertDialog(
      title: Text(payment.secondConfirmationTitle),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(payment.secondConfirmationBody),
          if (amount != null) ...[
            const SizedBox(height: SabSpacing.md),
            Text(
              SabMoney.format(amount!, currency: currency, locale: locale),
              style: SabTypography.h3.copyWith(
                color: SabColorTokens.of(context).textPrimary,
              ),
            ),
            const SizedBox(height: SabSpacing.xs),
            Text(
              payee,
              style: SabTypography.bodySmall.copyWith(
                color: SabColorTokens.of(context).textSecondary,
              ),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: Text(payment.cancel),
        ),
        SabButton(
          label: payment.confirmAndPay,
          onPressed: () => Navigator.of(context).pop(true),
        ),
      ],
    );
  }
}

/// The federal sub-panel: payer-reference entry and the switched-collection
/// notice (FEAT-006, C-030).
class _FederalPanel extends StatelessWidget {
  const _FederalPanel({
    required this.state,
    required this.payment,
    required this.referenceController,
    required this.serviceId,
  });

  final PaymentConfirmationState state;
  final PaymentStrings payment;
  final TextEditingController referenceController;
  final String serviceId;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
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
            _ReferenceField(
              controller: referenceController,
              payment: payment,
              serviceId: serviceId,
            ),
          ],
        ],
      ),
    );
  }
}

/// The payer-reference input for a federal collection. Kept stateful only to
/// submit on the field's done action.
class _ReferenceField extends ConsumerWidget {
  const _ReferenceField({
    required this.controller,
    required this.payment,
    required this.serviceId,
  });

  final TextEditingController controller;
  final PaymentStrings payment;
  final String serviceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SabTextField(
      label: payment.federalReferenceLabel,
      hint: payment.federalReferenceHint,
      controller: controller,
      textInputAction: TextInputAction.done,
      onSubmitted: (value) => ref
          .read(paymentControllerProvider(serviceId).notifier)
          .setReference(value),
    );
  }
}

/// The bill sub-panel: recipient entry and its validation outcome (FEAT-007,
/// C-033).
class _BillPanel extends StatelessWidget {
  const _BillPanel({
    required this.state,
    required this.payment,
    required this.recipientController,
    required this.serviceId,
  });

  final PaymentConfirmationState state;
  final PaymentStrings payment;
  final TextEditingController recipientController;
  final String serviceId;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final validation = state.billValidation;
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
            _RecipientField(
              controller: recipientController,
              payment: payment,
              serviceId: serviceId,
            )
          else ...[
            _ValueRow(
              label: payment.recipientLabel,
              value: state.recipient ?? '',
            ),
            if (validation != null && validation.valid) ...[
              const SizedBox(height: SabSpacing.sm),
              Text(
                payment.tokenStored,
                style: SabTypography.bodySmall.copyWith(
                  color: colors.textSecondary,
                ),
              ),
            ],
          ],
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

class _RecipientField extends ConsumerWidget {
  const _RecipientField({
    required this.controller,
    required this.payment,
    required this.serviceId,
  });

  final TextEditingController controller;
  final PaymentStrings payment;
  final String serviceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SabTextField(
      label: payment.recipientLabel,
      hint: payment.recipientHint,
      controller: controller,
      textInputAction: TextInputAction.done,
      onSubmitted: (value) => ref
          .read(paymentControllerProvider(serviceId).notifier)
          .setRecipient(value),
    );
  }
}

class _ValueRow extends StatelessWidget {
  const _ValueRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Row(
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
class _StateNotice extends ConsumerWidget {
  const _StateNotice({
    required this.state,
    required this.payment,
    required this.strings,
  });

  final PaymentConfirmationState state;
  final PaymentStrings payment;
  final SabStrings strings;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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
      PaymentPhase.failure => (
        SabIcons.statusFailed,
        colors.error500,
        payment.failureTitle,
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
    return SingleChildScrollView(
      padding: const EdgeInsets.all(SabSpacing.md),
      child: Container(
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
              label: verified
                  ? payment.receiptVerified
                  : payment.receiptUnverified,
            ),
          ],
        ),
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
