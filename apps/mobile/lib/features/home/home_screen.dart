import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../a2ui/a2ui_surface.dart';
import '../../a2ui/sabi_catalog.dart';
import '../../a2ui/surface_task.dart';
import '../../components/confirmation_summary.dart';
import '../../components/empty_state.dart';
import '../../components/error_state.dart';
import '../../components/offline_banner.dart';
import '../../components/receipt_card.dart';
import '../../components/reauth_dialog.dart';
import '../../components/sab_button.dart';
import '../../components/service_result_row.dart';
import '../../components/skeleton.dart';
import '../../components/status_pill.dart';
import '../../core/connectivity.dart';
import '../../core/reauth.dart';
import '../../data/providers.dart';
import '../../data/repositories.dart';
import '../../design_system/icons.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import '../../models/receipt_summary.dart';
import '../../models/service_summary.dart';
import '../account/verification/verification_task_view.dart';
import '../payment/payment_controller.dart';
import '../payment/payment_task_view.dart';
import 'home_controller.dart';

/// Screen 3: Home (`/home`). State a payment need, resolve it, and reach
/// confirmation from the composer at the base of the screen.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  final _composer = TextEditingController();
  final _composerFocus = FocusNode();
  final _conversationScroll = ScrollController();

  @override
  void dispose() {
    _composer.dispose();
    _composerFocus.dispose();
    _conversationScroll.dispose();
    super.dispose();
  }

  /// Keep the newest turn in view. A conversation that grows past the viewport
  /// must show the assistant's latest reply without a manual scroll, so the
  /// list follows the exchange in time order (screens.md, Home layout). The
  /// scroll is instant under the OS reduce-motion setting.
  void _scrollToLatest() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_conversationScroll.hasClients) return;
      final position = _conversationScroll.position;
      if (position.maxScrollExtent <= position.pixels) return;
      final target = position.maxScrollExtent;
      if (MediaQuery.disableAnimationsOf(context)) {
        _conversationScroll.jumpTo(target);
      } else {
        _conversationScroll.animateTo(
          target,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _send() async {
    final text = _composer.text;
    if (text.trim().isEmpty) return;
    _composer.clear();
    // The conversation resolves and renders the result inline. Several matches
    // are a composed provider picker, a single match a composed result row; in
    // both the user selects in the conversation rather than being sent to a
    // screen (FEAT-004, FEAT-011, D-050).
    await ref.read(homeControllerProvider.notifier).submit(text);
  }

  /// Selects a discovery result in the conversation: the turn composes its
  /// confirmation inline rather than navigating away.
  void _selectService(String serviceId) {
    ref.read(homeControllerProvider.notifier).selectService(serviceId);
  }

  /// Opens the existing receipt screen for a settled bill, the non-conversation
  /// route to the same record (FEAT-008).
  void _openReceipt(String receiptId) => context.push('/receipts/$receiptId');

  /// Opens the existing screen for a record the conversation rendered inline,
  /// so the user may take either route to the same record (user-flow Flow 9).
  void _openRecord(ResolvedRecord record) {
    if (record.isReceipt) {
      context.push('/receipts/${record.id}');
    } else {
      context.push('/cases/${record.id}');
    }
  }

  /// Opens the existing identity screen for a payment that is held pending
  /// verification; the inline surface carries the held state in the
  /// conversation, and the ceremony resumes the task on return.
  void _openVerification() =>
      context.push('/account/verify?from=payment');

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

  void _showSupport() {
    final strings = ref.read(sabStringsProvider);
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(strings.contactSupport),
        content: Text(strings.notCoveredBody),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(strings.close),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final strings = ref.watch(sabStringsProvider);
    final online = ref.watch(connectivityProvider);
    final state = ref.watch(homeControllerProvider);
    final recent = ref.watch(recentReceiptsProvider);

    ref.listen<bool>(reauthProvider, (previous, next) {
      if (next) _showReauth();
    });
    // Follow the exchange as it grows: every append or settle scrolls the
    // newest turn into view.
    ref.listen(homeControllerProvider, (previous, next) {
      if (previous?.turns != next.turns) _scrollToLatest();
    });

    return Scaffold(
      appBar: AppBar(
        title: Text(strings.homeTitle),
        actions: [
          IconButton(
            tooltip: strings.accountTooltip,
            icon: const SabIconView(SabIcons.account),
            onPressed: () => context.go('/account'),
          ),
        ],
      ),
      body: Column(
        children: [
          if (!online)
            OfflineBanner(
              message: strings.offlineNoPayment,
              queuedLabel: state.queued ? strings.queuedOffline : null,
            ),
          Expanded(
            child: recent.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(SabSpacing.md),
                child: SabSkeletonList(),
              ),
              error: (_, _) => ErrorState(
                message: strings.homeLoadError,
                retryLabel: strings.retry,
                onRetry: () => ref.invalidate(recentReceiptsProvider),
              ),
              data: (receipts) => _Conversation(
                receipts: receipts,
                state: state,
                scrollController: _conversationScroll,
                onSelectService: _selectService,
                onOpenReceipt: _openReceipt,
                onOpenRecord: _openRecord,
                onOpenVerification: _openVerification,
                onRetry: () =>
                    ref.read(homeControllerProvider.notifier).retry(),
                onSupport: _showSupport,
              ),
            ),
          ),
          _Composer(
            controller: _composer,
            focusNode: _composerFocus,
            enabled: state.phase != HomePhase.composing,
            onSend: _send,
          ),
        ],
      ),
    );
  }
}

class _Conversation extends ConsumerWidget {
  const _Conversation({
    required this.receipts,
    required this.state,
    required this.scrollController,
    required this.onSelectService,
    required this.onOpenReceipt,
    required this.onOpenRecord,
    required this.onOpenVerification,
    required this.onRetry,
    required this.onSupport,
  });

  final List<ReceiptSummary> receipts;
  final HomeState state;
  final ScrollController scrollController;

  /// Selects a discovery result in the conversation (never navigates).
  final ValueChanged<String> onSelectService;

  /// Opens the existing Receipt Detail screen for a settled bill.
  final ValueChanged<String> onOpenReceipt;
  final ValueChanged<ResolvedRecord> onOpenRecord;
  final VoidCallback onOpenVerification;
  final VoidCallback onRetry;
  final VoidCallback onSupport;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    final showEmpty = receipts.isEmpty && state.turns.isEmpty;

    if (showEmpty) {
      return EmptyState(
        title: strings.emptyTitle,
        message: strings.emptyBody,
        semanticLabel: strings.emptyTitle,
      );
    }

    return ListView(
      controller: scrollController,
      padding: const EdgeInsets.all(SabSpacing.md),
      children: [
        if (receipts.isNotEmpty) ...[
          Text(
            strings.recent.toUpperCase(),
            style: SabTypography.caption.copyWith(color: colors.textSecondary),
          ),
          const SizedBox(height: SabSpacing.sm),
          for (final receipt in receipts) ...[
            ReceiptCard(
              receipt: receipt,
              onTap: () => context.push('/receipts/${receipt.id}'),
            ),
            const SizedBox(height: SabSpacing.md),
          ],
        ],
        // Every turn stays on screen, oldest first, so the conversation builds
        // up in time order (screens.md, screen 3, Layout). The larger gap
        // between turns groups each request with its result.
        for (var i = 0; i < state.turns.length; i++) ...[
          if (i > 0) const SizedBox(height: SabSpacing.lg),
          _Turn(
            turn: state.turns[i],
            isLatest: i == state.turns.length - 1,
            onSelectService: onSelectService,
            onOpenReceipt: onOpenReceipt,
            onOpenRecord: onOpenRecord,
            onOpenVerification: onOpenVerification,
            onRetry: onRetry,
            onSupport: onSupport,
          ),
        ],
      ],
    );
  }
}

/// One conversation turn: the user's request followed by the assistant's
/// outcome for it. Every turn renders, so earlier requests and results remain
/// visible and are never discarded (screens.md, screen 3, Layout).
class _Turn extends ConsumerWidget {
  const _Turn({
    required this.turn,
    required this.isLatest,
    required this.onSelectService,
    required this.onOpenReceipt,
    required this.onOpenRecord,
    required this.onOpenVerification,
    required this.onRetry,
    required this.onSupport,
  });

  final ConversationTurn turn;

  /// A retry only makes sense for the request in front of the user; an earlier
  /// failed turn is history, so it renders its notice without the action.
  final bool isLatest;
  final ValueChanged<String> onSelectService;
  final ValueChanged<String> onOpenReceipt;
  final ValueChanged<ResolvedRecord> onOpenRecord;
  final VoidCallback onOpenVerification;
  final VoidCallback onRetry;
  final VoidCallback onSupport;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _RequestBubble(text: turn.request),
        const SizedBox(height: SabSpacing.md),
        switch (turn.phase) {
          HomePhase.idle => const SizedBox.shrink(),
          // The offline banner carries the queued explanation; the turn holds
          // the request itself so it is not lost when connectivity returns.
          HomePhase.queued => const SizedBox.shrink(),
          HomePhase.composing => Container(
            padding: const EdgeInsets.all(SabSpacing.md),
            decoration: BoxDecoration(
              color: colors.surfaceSecondary,
              borderRadius: BorderRadius.circular(SabRadii.md),
            ),
            child: Row(
              children: [
                const SizedBox(
                  width: SabSizes.iconMd,
                  height: SabSizes.iconMd,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: SabSpacing.sm),
                Text(
                  strings.composing,
                  style: SabTypography.body.copyWith(
                    color: colors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          HomePhase.discovery => _Discovery(
            turn: turn,
            onSelectService: onSelectService,
          ),
          HomePhase.confirmation => _Confirmation(
            turn: turn,
            onOpenVerification: onOpenVerification,
            onOpenReceipt: onOpenReceipt,
          ),
          HomePhase.verifying => _Verifying(
            turn: turn,
            onOpenVerification: onOpenVerification,
          ),
          HomePhase.recovering => _Recovering(
            turn: turn,
            onOpenRecord: onOpenRecord,
          ),
          HomePhase.record => _RecordLookup(
            turn: turn,
            onOpenRecord: onOpenRecord,
          ),
          HomePhase.noRecord => _Notice(
            title: strings.noRecordTitle,
            body: assistantReplyFor(turn, strings),
            actionLabel: strings.contactSupport,
            onAction: onSupport,
          ),
          HomePhase.clarifying => _Clarification(
            question: turn.intent?.reply,
            candidates: turn.candidates,
            onSelectService: onSelectService,
          ),
          HomePhase.conversational => _ConversationReply(
            text: assistantReplyFor(turn, strings),
          ),
          HomePhase.notCovered => _Notice(
            title: strings.notCoveredTitle,
            body: assistantReplyFor(turn, strings),
            actionLabel: strings.contactSupport,
            onAction: onSupport,
          ),
          HomePhase.error => _Notice(
            title: strings.somethingWrong,
            body: strings.sendFailed,
            actionLabel: strings.retry,
            onAction: isLatest ? onRetry : null,
          ),
        },
      ],
    );
  }
}

/// The composed discovery surface (FEAT-011). The agent composes the matching
/// Service Result Rows against the published catalog; the client renders them
/// through the GenUI SDK. When the surface is refused or the SDK cannot render
/// it, the same rows are rendered from the candidates the client already holds,
/// so the task stays completable.
class _Discovery extends StatelessWidget {
  const _Discovery({
    required this.turn,
    required this.onSelectService,
  });

  final ConversationTurn turn;

  /// Selects a result in the conversation: the controller composes its
  /// confirmation inline. Selecting never navigates (D-050).
  final ValueChanged<String> onSelectService;

  @override
  Widget build(BuildContext context) {
    return A2uiSurfaceView(
      stream: turn.surface,
      onAction: (action) {
        if (action.name == SabiActions.selectService) {
          final id = action.context['serviceId']?.toString();
          if (id != null && id.isNotEmpty) onSelectService(id);
        }
      },
      fallback: (context) => _DiscoveryFallback(
        candidates: turn.candidates,
        onSelectService: onSelectService,
      ),
    );
  }
}

/// The prewritten discovery fallback: the selectable result rows the client
/// already resolved, rendered without the SDK.
class _DiscoveryFallback extends StatelessWidget {
  const _DiscoveryFallback({
    required this.candidates,
    required this.onSelectService,
  });

  final List<ServiceSummary> candidates;
  final ValueChanged<String> onSelectService;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final service in candidates) ...[
          ServiceResultRow(
            service: service,
            onSelect: () => onSelectService(service.serviceId),
          ),
          const SizedBox(height: SabSpacing.sm),
        ],
      ],
    );
  }
}

/// The payment task composed inline (FEAT-005/011, screens/03-home.md
/// "Confirmation inline"). A variable amount first composes its `AmountEntry`
/// surface inline; the confirmation then renders the agent-composed summary (or
/// its prewritten fallback) with the client-owned authorise action and every
/// payment state, driven by the payment controller. The confirmation gate is
/// unchanged: the authorise action is the explicit confirmation, and no payment
/// is submitted without it.
class _Confirmation extends ConsumerWidget {
  const _Confirmation({
    required this.turn,
    required this.onOpenVerification,
    required this.onOpenReceipt,
  });

  final ConversationTurn turn;

  /// Opens the Identity screen for a payment held pending verification.
  final VoidCallback onOpenVerification;

  /// Opens the existing Receipt Detail screen for a settled bill.
  final ValueChanged<String> onOpenReceipt;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final intent = turn.intent;
    final service = turn.selectedService;
    final serviceId = service?.serviceId;

    Widget summaryFallback(BuildContext context) => ConfirmationSummary(
      // The selected service's own known amount is the grounded source; the
      // intent amount covers a task-named confirmation.
      amount: service?.knownAmount ?? intent?.amount ?? 0,
      currency: service?.currency ?? intent?.currency ?? 'NGN',
      payee: service?.collectingBody ?? intent?.target ?? '',
      reference: intent?.reference,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (intent?.hasReply ?? false) ...[
          _ConversationReply(text: intent!.reply!),
          const SizedBox(height: SabSpacing.md),
        ],
        if (serviceId == null)
          // No resolved service to bind the mandate to: show the composed
          // summary only, with no authorise action.
          A2uiSurfaceView(
            stream: turn.surface,
            fallback: summaryFallback,
          )
        else if (turn.surfaceTask == SurfaceTask.amountEntry)
          _InlineAmountEntry(turn: turn, serviceId: serviceId)
        else
          PaymentTaskView(
            serviceId: serviceId,
            surface: turn.surface,
            summaryFallback: summaryFallback,
            onOpenVerification: onOpenVerification,
            onOpenReceipt: onOpenReceipt,
          ),
      ],
    );
  }
}

/// The variable-amount task composed inline (FEAT-005/011). The agent composes
/// the `AmountEntry` surface with the biller's C-033 range when one is known;
/// the prewritten fallback is the client's inline amount field. Submitting binds
/// the amount to the payment controller and moves the turn to its confirmation.
class _InlineAmountEntry extends ConsumerWidget {
  const _InlineAmountEntry({required this.turn, required this.serviceId});

  final ConversationTurn turn;
  final String serviceId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final range = ref
        .watch(paymentControllerProvider(serviceId))
        .billValidation
        ?.range;
    return A2uiSurfaceView(
      stream: turn.surface,
      onAction: (action) {
        if (action.name == SabiActions.submitAmount) {
          final amount = action.context['amount'];
          if (amount is num) {
            ref.read(homeControllerProvider.notifier).setAmount(amount.toInt());
          }
        }
      },
      fallback: (context) => SabAmountEntryField(
        strings: strings,
        minimum: range?.minimum,
        maximum: range?.maximum,
        onSubmit: (minor) =>
            ref.read(homeControllerProvider.notifier).setAmount(minor),
      ),
    );
  }
}

/// The identity-verification task composed inline (FEAT-002, FEAT-011,
/// screens/03-home.md "Verifying inline"). The agent composes the verification
/// surface above; below it the shared [VerificationTaskView] drives the
/// verification controller, so the ceremony — collect the NIN/BVN, submit
/// (C-020/C-021), and show the resulting status (C-022) — completes in the
/// conversation. The Identity screen stays the alternate route, reachable from
/// the composed surface and from Account.
class _Verifying extends ConsumerWidget {
  const _Verifying({required this.turn, required this.onOpenVerification});

  final ConversationTurn turn;
  final VoidCallback onOpenVerification;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        A2uiSurfaceView(
          stream: turn.surface,
          onAction: (action) {
            if (action.name == SabiActions.openVerification) {
              onOpenVerification();
            }
          },
          fallback: (context) => _TaskCard(
            title: strings.verifyInlineTitle,
            body: assistantReplyFor(turn, strings),
            actionLabel: strings.openVerificationScreen,
            onAction: onOpenVerification,
          ),
        ),
        const SizedBox(height: SabSpacing.md),
        // The ceremony is the prewritten shell for the composed surface: the
        // controller is the state machine and this view dispatches its actions,
        // so the task completes inline rather than leaving for the screen.
        const VerificationTaskView(showHeading: false),
      ],
    );
  }
}

/// The failed-payment or case recovery task composed inline (FEAT-011,
/// screens/03-home.md "Recovering inline"). The agent composes the recovery
/// surface; the case may also be opened on its screen, the alternate route.
class _Recovering extends ConsumerWidget {
  const _Recovering({
    required this.turn,
    required this.onOpenRecord,
  });

  final ConversationTurn turn;
  final ValueChanged<ResolvedRecord> onOpenRecord;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final caseId = turn.record?.caseSummary?.caseId;
    final record = turn.record;
    return A2uiSurfaceView(
      stream: turn.surface,
      onAction: (action) {
        if (action.name == SabiActions.openCase &&
            record != null &&
            caseId != null) {
          onOpenRecord(record);
        }
      },
      fallback: (context) => _TaskCard(
        title: strings.recoveringTitle,
        body: assistantReplyFor(turn, strings),
        actionLabel: caseId == null ? null : strings.openCase,
        onAction: caseId == null || record == null
            ? null
            : () => onOpenRecord(record),
      ),
    );
  }
}

/// A resolved record lookup rendered inline (FEAT-003, FEAT-023; user-flow
/// Flow 9): a single match as a composed record surface, several as candidates
/// the user chooses from, each able to open the existing screen instead. No
/// match renders no record surface (that is [HomePhase.noRecord]).
class _RecordLookup extends ConsumerWidget {
  const _RecordLookup({required this.turn, required this.onOpenRecord});

  final ConversationTurn turn;
  final ValueChanged<ResolvedRecord> onOpenRecord;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);

    final single = turn.record;
    if (single != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (turn.intent?.hasReply ?? false) ...[
            _ConversationReply(text: turn.intent!.reply!),
            const SizedBox(height: SabSpacing.md),
          ],
          A2uiSurfaceView(
            stream: turn.surface,
            onAction: (action) {
              if (action.name == SabiActions.openRecord) {
                onOpenRecord(single);
              }
            },
            fallback: (context) =>
                _RecordFallback(record: single, onOpenRecord: onOpenRecord),
          ),
          if (single.isReceipt) ...[
            const SizedBox(height: SabSpacing.sm),
            SabButton(
              label: strings.openReceipt,
              variant: SabButtonVariant.ghost,
              onPressed: () => onOpenRecord(single),
            ),
          ],
        ],
      );
    }

    // Several matches: the user chooses which to open rather than the assistant
    // guessing. Each is a real record from the owner's own records, rendered as
    // the per-record fallback form (a candidate set is not a single surface).
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (turn.intent?.hasReply ?? false) ...[
          _ConversationReply(text: turn.intent!.reply!),
          const SizedBox(height: SabSpacing.md),
        ],
        Text(
          strings.recordCandidatesTitle,
          style: SabTypography.body.copyWith(
            color: colors.textPrimary,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: SabSpacing.sm),
        for (final record in turn.records) ...[
          _RecordFallback(record: record, onOpenRecord: onOpenRecord),
          const SizedBox(height: SabSpacing.sm),
        ],
      ],
    );
  }
}

/// The prewritten record fallback: a receipt renders the client's Receipt Card;
/// a case renders its reference and state. It shows the record's own fields,
/// never a message, and keeps the record openable.
class _RecordFallback extends StatelessWidget {
  const _RecordFallback({required this.record, required this.onOpenRecord});

  final ResolvedRecord record;
  final ValueChanged<ResolvedRecord> onOpenRecord;

  @override
  Widget build(BuildContext context) {
    final receipt = record.receipt;
    if (receipt != null) {
      return Semantics(
        button: true,
        label: receipt.payee,
        child: ReceiptCard(
          receipt: receipt,
          onTap: () => onOpenRecord(record),
        ),
      );
    }
    final paymentCase = record.caseSummary;
    if (paymentCase != null) {
      return Semantics(
        button: true,
        label: paymentCase.caseId,
        child: _TaskCard(
          title: paymentCase.type.wire,
          body: paymentCase.paymentId,
          status: _pillStatus(paymentCase.status.wire),
          actionLabel: '',
          onAction: () => onOpenRecord(record),
        ),
      );
    }
    return const SizedBox.shrink();
  }
}

/// Maps a case status to the Status Pill's vocabulary so the record surface
/// pairs a colour with a label and a glyph (branding.md, "Accessibility").
String _pillStatus(String wire) => switch (wire) {
  'resolved' || 'closed' => 'settled',
  'escalated' => 'failed',
  'awaiting_provider' => 'awaiting_receipt',
  _ => 'pending',
};

/// Maps a status-pill wire value to the [SabStatus] vocabulary.
SabStatus _statusFrom(String wire) => switch (wire) {
  'settled' => SabStatus.settled,
  'failed' => SabStatus.failed,
  'awaiting_receipt' || 'awaitingReceipt' => SabStatus.awaitingReceipt,
  'unverified' => SabStatus.unverified,
  'verified' => SabStatus.verified,
  'suspended' => SabStatus.suspended,
  _ => SabStatus.pending,
};

/// A prewritten inline task card: a titled state with a single next action.
/// Used by the verification and recovery surfaces whose task state is text and
/// whose completion action is a route to the equal screen.
class _TaskCard extends StatelessWidget {
  const _TaskCard({
    required this.title,
    this.body,
    this.status,
    this.actionLabel,
    this.onAction,
  });

  final String title;
  final String? body;
  final String? status;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Container(
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.surfaceSecondary,
        borderRadius: BorderRadius.circular(SabRadii.md),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: SabTypography.body.copyWith(
              color: colors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (body != null && body!.isNotEmpty) ...[
            const SizedBox(height: SabSpacing.xs),
            Text(
              body!,
              style: SabTypography.bodySmall.copyWith(
                color: colors.textSecondary,
              ),
            ),
          ],
          if (status != null) ...[
            const SizedBox(height: SabSpacing.sm),
            StatusPill(status: _statusFrom(status!)),
          ],
          if (actionLabel != null && actionLabel!.isNotEmpty) ...[
            const SizedBox(height: SabSpacing.sm),
            SabButton(
              label: actionLabel!,
              variant: SabButtonVariant.ghost,
              onPressed: onAction,
            ),
          ],
        ],
      ),
    );
  }
}

class _Clarification extends ConsumerWidget {
  const _Clarification({
    required this.question,
    required this.candidates,
    required this.onSelectService,
  });

  final String? question;
  final List<ServiceSummary> candidates;

  /// Selecting one of the closest matches resolves it in the conversation
  /// rather than leaving for a screen.
  final ValueChanged<String> onSelectService;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    return Container(
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.info100,
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            strings.clarifyingTitle,
            style: SabTypography.body.copyWith(
              color: colors.info900,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (question != null) ...[
            const SizedBox(height: SabSpacing.xs),
            Text(
              question!,
              style: SabTypography.body.copyWith(color: colors.info900),
            ),
          ],
          // A no-candidate clarification is just the question: the "Closest
          // matches" caption and its spacing carry no information and would
          // render as an empty label, so they only appear with candidates.
          if (candidates.isNotEmpty) ...[
            const SizedBox(height: SabSpacing.md),
            Text(
              strings.candidates.toUpperCase(),
              style: SabTypography.caption.copyWith(color: colors.info900),
            ),
            const SizedBox(height: SabSpacing.sm),
            for (final service in candidates) ...[
              ServiceResultRow(
                service: service,
                onSelect: () => onSelectService(service.serviceId),
              ),
              const SizedBox(height: SabSpacing.sm),
            ],
          ],
        ],
      ),
    );
  }
}

/// The assistant's conversational reply to a non-command message, mirroring the
/// user bubble on the opposite side so the reply reads as one exchange
/// (screens.md, Home "Conversational").
class _ConversationReply extends StatelessWidget {
  const _ConversationReply({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: SabSizes.contentMaxWidth),
        padding: const EdgeInsets.symmetric(
          horizontal: SabSpacing.md,
          vertical: SabSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: colors.surfaceSecondary,
          borderRadius: BorderRadius.circular(SabRadii.lg),
          border: Border.all(color: colors.border),
        ),
        child: Text(
          text,
          style: SabTypography.body.copyWith(color: colors.textPrimary),
        ),
      ),
    );
  }
}

/// The user's own words, shown above the result so the conversation reads in
/// order (screens.md, Home layout).
class _RequestBubble extends StatelessWidget {
  const _RequestBubble({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: const BoxConstraints(maxWidth: SabSizes.contentMaxWidth),
        padding: const EdgeInsets.symmetric(
          horizontal: SabSpacing.md,
          vertical: SabSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: colors.primary100,
          borderRadius: BorderRadius.circular(SabRadii.lg),
        ),
        child: Text(
          text,
          style: SabTypography.body.copyWith(color: colors.primary900),
        ),
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({
    required this.title,
    required this.body,
    this.actionLabel,
    this.onAction,
  });

  final String title;
  final String body;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Container(
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.surfaceSecondary,
        borderRadius: BorderRadius.circular(SabRadii.md),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: SabTypography.body.copyWith(
              color: colors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: SabSpacing.xs),
          Text(
            body,
            style: SabTypography.bodySmall.copyWith(
              color: colors.textSecondary,
            ),
          ),
          if (actionLabel != null) ...[
            const SizedBox(height: SabSpacing.sm),
            SabButton(
              label: actionLabel!,
              variant: SabButtonVariant.ghost,
              onPressed: onAction,
            ),
          ],
        ],
      ),
    );
  }
}

class _Composer extends ConsumerWidget {
  const _Composer({
    required this.controller,
    required this.focusNode,
    required this.enabled,
    required this.onSend,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool enabled;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    return Container(
      decoration: BoxDecoration(
        color: colors.surface,
        border: Border(top: BorderSide(color: colors.border)),
      ),
      padding: const EdgeInsets.symmetric(
        horizontal: SabSpacing.md,
        vertical: SabSpacing.sm,
      ),
      child: SafeArea(
        top: false,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: ValueListenableBuilder<TextEditingValue>(
                valueListenable: controller,
                builder: (context, value, _) => TextField(
                  controller: controller,
                  focusNode: focusNode,
                  enabled: enabled,
                  minLines: 1,
                  maxLines: 4,
                  maxLength: homeRequestMaxLength,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => onSend(),
                  style: SabTypography.body.copyWith(color: colors.textPrimary),
                  // The bound only matters as it approaches; until then the
                  // counter is noise, so it stays hidden (screens.md, very
                  // long free-form input).
                  buildCounter:
                      (
                        context, {
                        required currentLength,
                        required isFocused,
                        maxLength,
                      }) => currentLength < homeRequestMaxLength - 20
                      ? null
                      : Text(
                          '$currentLength/$maxLength',
                          style: SabTypography.caption.copyWith(
                            color: colors.textSecondary,
                          ),
                        ),
                  decoration: InputDecoration(hintText: strings.composerHint),
                ),
              ),
            ),
            const SizedBox(width: SabSpacing.sm),
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: controller,
              builder: (context, value, _) {
                final canSend = enabled && value.text.trim().isNotEmpty;
                return Semantics(
                  button: true,
                  enabled: canSend,
                  label: strings.send,
                  child: SizedBox(
                    width: SabSizes.minTouchTarget,
                    height: SabSizes.minTouchTarget,
                    child: IconButton(
                      onPressed: canSend ? onSend : null,
                      icon: const SabIconView(SabIcons.send),
                      color: colors.primary500,
                      disabledColor: colors.textSecondary,
                      tooltip: strings.send,
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
