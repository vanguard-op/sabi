import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../components/sab_button.dart';
import '../../../components/sab_text_field.dart';
import '../../../components/section_card.dart';
import '../../../components/skeleton.dart';
import '../../../components/status_pill.dart';
import '../../../core/connectivity.dart';
import '../../../design_system/icons.dart';
import '../../../design_system/tokens.dart';
import '../account_screen.dart' show accountProvider;
import 'verification_controller.dart';
import 'verification_models.dart';
import 'verification_strings.dart';

/// The identity ceremony rendered inline in the conversation (FEAT-002,
/// FEAT-011). It is the prewritten shell for the composed `Verification`
/// surface: the agent-composed surface (or its fallback) sits above it, and this
/// view owns the client chrome — the NIN/BVN fields, the submit and correction
/// actions, and every state the check moves through.
///
/// It drives [verificationControllerProvider], which holds the state machine,
/// so no verification state is re-derived here: the view renders the
/// controller's phase and dispatches its actions. The same widget is the body of
/// the Identity Verification screen, so the conversation and the screen cannot
/// drift apart. The C-020/C-021/C-022 calls are the repository calls the
/// controller makes; the view only collects the details and shows the result.
class VerificationTaskView extends ConsumerStatefulWidget {
  const VerificationTaskView({
    super.key,
    this.fromPayment = false,
    this.onExit,
    this.showHeading = true,
  });

  /// True when the ceremony was opened from a payment held for KYC, so a match
  /// resumes the payment and the held notice is shown.
  final bool fromPayment;

  /// The exit action for a host screen (back to Account, or to the held
  /// payment). Null inline in the conversation, which continues in place.
  final VoidCallback? onExit;

  /// Whether the view renders its own prewritten heading and intro. Inline the
  /// agent-composed surface above carries the framing, so the heading is
  /// suppressed to avoid repeating it; the screen keeps it.
  final bool showHeading;

  @override
  ConsumerState<VerificationTaskView> createState() =>
      _VerificationTaskViewState();
}

class _VerificationTaskViewState extends ConsumerState<VerificationTaskView> {
  final _nin = TextEditingController();
  final _bvn = TextEditingController();

  /// The last authoritative status this view already propagated to the account
  /// cache, so a rebuild or a repeat read does not invalidate again.
  KycStatus? _syncedKyc;

  @override
  void dispose() {
    _nin.dispose();
    _bvn.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = ref.watch(verificationStringsProvider);
    final online = ref.watch(connectivityProvider);
    final state = ref.watch(verificationControllerProvider);

    // Mirror connectivity into the controller so a submit is refused offline
    // and a load retries when the connection returns.
    ref.listen<bool>(connectivityProvider, (_, next) {
      ref.read(verificationControllerProvider.notifier).setOnline(next);
    });

    // A check changes the account's stored verification status (C-008), but
    // `accountProvider` caches the record it fetched when Account first loaded;
    // without this it would still render the old status on return (FEAT-002,
    // screens/09 "Verified", screens/05 "Transition on success"). Listening to
    // the controller covers every path that reaches the outcome — load, submit
    // result, and poll result — in one place, and Account keeps reading the
    // authoritative record rather than this view's transient phase.
    ref.listen<VerificationState>(verificationControllerProvider, (_, next) {
      switch (next.status?.kycStatus) {
        case KycStatus.verified:
        case KycStatus.pending:
          final status = next.status!.kycStatus;
          if (_syncedKyc != status) {
            _syncedKyc = status;
            ref.invalidate(accountProvider);
          }
        case KycStatus.unverified || KycStatus.rejected || null:
          _syncedKyc = null;
      }
    });

    if (state.phase == VerificationPhase.loading) {
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

    return _Body(
      state: state,
      online: online,
      strings: strings,
      fromPayment: widget.fromPayment,
      showHeading: widget.showHeading,
      onExit: widget.onExit,
      nin: _nin,
      bvn: _bvn,
      onVerify: _verify,
      onCorrect: () => ref
          .read(verificationControllerProvider.notifier)
          .correct(),
      onSupport: _showSupport,
      onRetryLoad: () => ref
          .read(verificationControllerProvider.notifier)
          .load(),
    );
  }

  Future<void> _verify(VerificationMethod method) async {
    final state = ref.read(verificationControllerProvider);
    if (!state.canSubmit) return;
    final identifier = method == VerificationMethod.bvn ? _bvn.text : _nin.text;
    await ref
        .read(verificationControllerProvider.notifier)
        .submit(method: method, identifier: identifier);
  }

  void _showSupport() {
    final strings = ref.read(verificationStringsProvider);
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(strings.contactSupport),
        content: Text(strings.rejectedBody),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(MaterialLocalizations.of(context).closeButtonLabel),
          ),
        ],
      ),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({
    required this.state,
    required this.online,
    required this.strings,
    required this.fromPayment,
    required this.showHeading,
    required this.onExit,
    required this.nin,
    required this.bvn,
    required this.onVerify,
    required this.onCorrect,
    required this.onSupport,
    required this.onRetryLoad,
  });

  final VerificationState state;
  final bool online;
  final VerificationStrings strings;
  final bool fromPayment;
  final bool showHeading;
  final VoidCallback? onExit;
  final TextEditingController nin;
  final TextEditingController bvn;
  final ValueChanged<VerificationMethod> onVerify;
  final VoidCallback onCorrect;
  final VoidCallback onSupport;
  final VoidCallback onRetryLoad;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final status = state.status;

    if (state.phase == VerificationPhase.error) {
      return _Failure(
        message: strings.loadError,
        retryLabel: strings.retry,
        onRetry: onRetryLoad,
      );
    }

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: SabSizes.contentMaxWidth),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _StatusHeader(
              status: status?.kycStatus ?? KycStatus.unverified,
              title: _title(state, strings),
              strings: strings,
              showHeading: showHeading,
            ),
            const SizedBox(height: SabSpacing.lg),
            // Inline the agent-composed surface above frames the task, so the
            // prewritten intro is the screen's framing and only repeats it.
            if (showHeading || state.phase != VerificationPhase.ready)
              Text(
                _intro(state, strings),
                style: SabTypography.body.copyWith(
                  color: colors.textSecondary,
                ),
              ),
            if (state.phase == VerificationPhase.noMatch) ...[
              const SizedBox(height: SabSpacing.md),
              _ReasonCard(
                title: strings.noMatchTitle,
                body: state.reason ?? strings.noMatchBody,
              ),
            ],
            if (state.phase == VerificationPhase.rejected) ...[
              const SizedBox(height: SabSpacing.md),
              _ReasonCard(
                title: strings.rejectedTitle,
                body: state.reason ?? strings.rejectedBody,
              ),
            ],
            if (fromPayment && state.phase != VerificationPhase.verified) ...[
              const SizedBox(height: SabSpacing.md),
              _HeldPaymentNotice(strings: strings),
            ],
            const SizedBox(height: SabSpacing.lg),
            ..._actions(context),
          ],
        ),
      ),
    );
  }

  List<Widget> _actions(BuildContext context) {
    switch (state.phase) {
      case VerificationPhase.verified:
        if (onExit == null) return const [SizedBox.shrink()];
        return [
          SabButton(
            label: fromPayment ? strings.resumePayment : strings.backToAccount,
            icon: fromPayment ? SabIcons.chevronRight : null,
            expand: true,
            onPressed: onExit,
          ),
        ];
      case VerificationPhase.pendingProvider:
        if (onExit == null) return const [SizedBox.shrink()];
        return [
          SabButton(
            label: strings.backToAccount,
            variant: SabButtonVariant.ghost,
            expand: true,
            onPressed: onExit,
          ),
        ];
      case VerificationPhase.rejected:
        return [
          SabButton(
            label: strings.contactSupport,
            icon: SabIcons.help,
            expand: true,
            onPressed: onSupport,
          ),
          if (onExit != null) ...[
            const SizedBox(height: SabSpacing.sm),
            SabButton(
              label: strings.backToAccount,
              variant: SabButtonVariant.ghost,
              expand: true,
              onPressed: onExit,
            ),
          ],
        ];
      case VerificationPhase.noMatch:
        if (!state.canCorrect) {
          // A second failed correction stops at support rather than looping
          // (FEAT-002, screens/05 "Edge Cases").
          return [
            SabButton(
              label: strings.contactSupport,
              icon: SabIcons.help,
              expand: true,
              onPressed: onSupport,
            ),
            if (onExit != null) ...[
              const SizedBox(height: SabSpacing.sm),
              SabButton(
                label: strings.backToAccount,
                variant: SabButtonVariant.ghost,
                expand: true,
                onPressed: onExit,
              ),
            ],
          ];
        }
        return [
          SabButton(
            label: strings.correctDetails,
            expand: true,
            onPressed: onCorrect,
          ),
        ];
      case VerificationPhase.ready:
      case VerificationPhase.checking:
        return _form(context);
      case VerificationPhase.loading:
      case VerificationPhase.error:
        return const [SizedBox.shrink()];
    }
  }

  List<Widget> _form(BuildContext context) {
    final checking = state.phase == VerificationPhase.checking;
    final bvnRequired = state.status?.method == VerificationMethod.bvn;
    return [
      SectionCard(
        title: strings.formGroup,
        children: [
          SabTextField(
            label: strings.ninLabel,
            hint: strings.ninHint,
            controller: nin,
            enabled: !checking,
            keyboardType: TextInputType.number,
            textInputAction: bvnRequired
                ? TextInputAction.next
                : TextInputAction.done,
            errorText: state.identifierError == null
                ? null
                : (state.identifierError == 'invalid'
                      ? strings.invalidNin
                      : strings.requiredField),
            onSubmitted: (_) {
              if (!bvnRequired) onVerify(VerificationMethod.nin);
            },
          ),
          if (bvnRequired) ...[
            const SizedBox(height: SabSpacing.md),
            SabTextField(
              label: strings.bvnLabel,
              hint: strings.bvnHint,
              controller: bvn,
              enabled: !checking,
              keyboardType: TextInputType.number,
              textInputAction: TextInputAction.done,
              helperText: strings.bvnNote,
              onSubmitted: (_) => onVerify(VerificationMethod.bvn),
            ),
          ],
        ],
      ),
      const SizedBox(height: SabSpacing.lg),
      if (online)
        SabButton(
          label: checking ? strings.verifying : strings.verify,
          loading: checking,
          expand: true,
          onPressed: state.canSubmit && !checking
              ? () => onVerify(
                  bvnRequired ? VerificationMethod.bvn : VerificationMethod.nin,
                )
              : null,
        )
      else
        // The action is genuinely unavailable offline, so it is not shown as a
        // live control; the offline banner explains why. This avoids an
        // enabled-looking button that cannot act.
        _OfflineActionNote(text: strings.offlineAction),
      if (checking) ...[
        const SizedBox(height: SabSpacing.sm),
        // The button carries the progress spinner; this live region names the
        // step for assistive tech and for anyone who cannot see the spinner.
        Semantics(
          liveRegion: true,
          child: Text(
            strings.verifying,
            textAlign: TextAlign.center,
            style: SabTypography.bodySmall.copyWith(
              color: SabColorTokens.of(context).textSecondary,
            ),
          ),
        ),
      ],
      const SizedBox(height: SabSpacing.lg),
      _DataUseNote(title: strings.dataUse, body: strings.dataUseBody),
    ];
  }

  String _title(VerificationState state, VerificationStrings strings) {
    return switch (state.phase) {
      VerificationPhase.verified => strings.verifiedTitle,
      VerificationPhase.pendingProvider => strings.pendingTitle,
      _ => strings.heading,
    };
  }

  String _intro(VerificationState state, VerificationStrings strings) {
    return switch (state.phase) {
      VerificationPhase.verified => strings.verifiedBody,
      VerificationPhase.pendingProvider => strings.pendingBody,
      VerificationPhase.rejected => strings.introRejected,
      VerificationPhase.noMatch => strings.introUnverified,
      _ => strings.introUnverified,
    };
  }
}

/// The status header: the Status Pill plus the state heading, so the pill is
/// never the only carrier of the state (branding.md, "Accessibility").
class _StatusHeader extends StatelessWidget {
  const _StatusHeader({
    required this.status,
    required this.title,
    required this.strings,
    required this.showHeading,
  });

  final KycStatus status;
  final String title;
  final VerificationStrings strings;
  final bool showHeading;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    // The heading is the ready-state framing; inline the agent-composed surface
    // above already carries it, so it is only repeated when the screen hosts
    // the view. A resolved state always names itself.
    final heading = title != strings.heading;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        StatusPill(status: _pill(), label: _label()),
        if (showHeading || heading) ...[
          const SizedBox(height: SabSpacing.sm),
          Text(
            title,
            style: SabTypography.h2.copyWith(color: colors.textPrimary),
          ),
        ],
      ],
    );
  }

  SabStatus _pill() => switch (status) {
    KycStatus.verified => SabStatus.verified,
    KycStatus.pending => SabStatus.pending,
    // The pill has no dedicated rejected state; the failed styling carries the
    // error colour and the label names it, so colour is never the only signal.
    KycStatus.rejected => SabStatus.failed,
    KycStatus.unverified => SabStatus.unverified,
  };

  String _label() => switch (status) {
    KycStatus.verified => strings.statusVerified,
    KycStatus.pending => strings.statusPending,
    KycStatus.rejected => strings.statusRejected,
    KycStatus.unverified => strings.statusUnverified,
  };
}

/// A held payment is not a failure; the notice says so and the surface stays
/// completable (screens/04, "Held for KYC").
class _HeldPaymentNotice extends StatelessWidget {
  const _HeldPaymentNotice({required this.strings});

  final VerificationStrings strings;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Container(
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.info100,
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SabIconView(
            SabIcons.info,
            size: SabSizes.iconMd,
            color: colors.info900,
          ),
          const SizedBox(width: SabSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  strings.heldPaymentNotice,
                  style: SabTypography.body.copyWith(
                    color: colors.info900,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: SabSpacing.xs),
                Text(
                  strings.heldPaymentBody,
                  style: SabTypography.bodySmall.copyWith(
                    color: colors.info900,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Shown in place of the primary action while the device is offline: the
/// action cannot run, so the surface says so rather than showing a live-looking
/// button that does nothing.
class _OfflineActionNote extends StatelessWidget {
  const _OfflineActionNote({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        SabIconView(
          SabIcons.offline,
          size: SabSizes.iconSm,
          color: colors.textSecondary,
        ),
        const SizedBox(width: SabSpacing.sm),
        Flexible(
          child: Text(
            text,
            style: SabTypography.bodySmall.copyWith(
              color: colors.textSecondary,
            ),
          ),
        ),
      ],
    );
  }
}

class _ReasonCard extends StatelessWidget {
  const _ReasonCard({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Container(
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.error100,
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              SabIconView(
                SabIcons.error,
                size: SabSizes.iconSm,
                color: colors.error900,
              ),
              const SizedBox(width: SabSpacing.sm),
              Expanded(
                child: Text(
                  title,
                  style: SabTypography.body.copyWith(
                    color: colors.error900,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: SabSpacing.xs),
          Text(
            body,
            style: SabTypography.bodySmall.copyWith(color: colors.error900),
          ),
        ],
      ),
    );
  }
}

/// The tertiary data-use note: how identity data is handled and retained
/// (screens/05, "Action Hierarchy": Tertiary).
class _DataUseNote extends StatelessWidget {
  const _DataUseNote({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            SabIconView(
              SabIcons.info,
              size: SabSizes.iconSm,
              color: colors.textSecondary,
            ),
            const SizedBox(width: SabSpacing.sm),
            Expanded(
              child: Text(
                title,
                style: SabTypography.bodySmall.copyWith(
                  color: colors.textPrimary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: SabSpacing.xs),
        Text(
          body,
          style: SabTypography.bodySmall.copyWith(color: colors.textSecondary),
        ),
      ],
    );
  }
}

/// A load failure with a retry, preserving the route (screens.md, Error State).
class _Failure extends StatelessWidget {
  const _Failure({
    required this.message,
    required this.retryLabel,
    required this.onRetry,
  });

  final String message;
  final String retryLabel;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(SabSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SabIconView(SabIcons.error, size: SabSizes.iconLg),
            const SizedBox(height: SabSpacing.lg),
            Text(
              message,
              textAlign: TextAlign.center,
              style: SabTypography.body.copyWith(color: colors.textSecondary),
            ),
            const SizedBox(height: SabSpacing.lg),
            SabButton(label: retryLabel, onPressed: onRetry),
          ],
        ),
      ),
    );
  }
}
