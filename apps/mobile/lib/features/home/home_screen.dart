import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/composed_task_surface.dart';
import '../../components/empty_state.dart';
import '../../components/error_state.dart';
import '../../components/offline_banner.dart';
import '../../components/provider_picker_sheet.dart';
import '../../components/receipt_card.dart';
import '../../components/reauth_dialog.dart';
import '../../components/sab_button.dart';
import '../../components/service_result_row.dart';
import '../../components/skeleton.dart';
import '../../core/connectivity.dart';
import '../../core/reauth.dart';
import '../../data/providers.dart';
import '../../design_system/icons.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import '../../models/composed_surface.dart';
import '../../models/receipt_summary.dart';
import '../../models/service_summary.dart';
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

  @override
  void dispose() {
    _composer.dispose();
    _composerFocus.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _composer.text;
    if (text.trim().isEmpty) return;
    _composer.clear();
    final controller = ref.read(homeControllerProvider.notifier);
    final candidates = await controller.submit(text);
    if (!mounted || candidates == null) return;
    // More than one collecting body is ambiguous: the picker blocks until a
    // choice is made, and the conversation underneath is preserved (screens.md).
    if (candidates.length > 1) {
      final chosen = await showSabProviderPickerSheet(
        context,
        candidates: candidates,
      );
      if (chosen != null && mounted) _openService(chosen.serviceId);
    }
    // A single match stays on the composed discovery surface as a selectable
    // row, so the user still confirms the target (FEAT-004).
  }

  void _openService(String serviceId) => context.push('/pay/$serviceId');

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
                onOpenService: _openService,
                onRetry: () => ref.read(homeControllerProvider.notifier).retry(),
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
    required this.onOpenService,
    required this.onRetry,
    required this.onSupport,
  });

  final List<ReceiptSummary> receipts;
  final HomeState state;
  final ValueChanged<String> onOpenService;
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
            onOpenService: onOpenService,
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
    required this.onOpenService,
    required this.onRetry,
    required this.onSupport,
  });

  final ConversationTurn turn;

  /// A retry only makes sense for the request in front of the user; an earlier
  /// failed turn is history, so it renders its notice without the action.
  final bool isLatest;
  final ValueChanged<String> onOpenService;
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
            candidates: turn.candidates,
            onOpenService: onOpenService,
          ),
          HomePhase.clarifying => _Clarification(
            question: turn.intent?.clarifyingQuestion,
            candidates: turn.candidates,
            onOpenService: onOpenService,
          ),
          HomePhase.notCovered => _Notice(
            title: strings.notCoveredTitle,
            body: strings.notCoveredBody,
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

/// The composed discovery surface (FEAT-011). The agent names only catalogue
/// components; an unknown component is refused and the fallback form keeps the
/// task completable.
class _Discovery extends StatelessWidget {
  const _Discovery({
    required this.candidates,
    required this.onOpenService,
  });

  final List<ServiceSummary> candidates;
  final ValueChanged<String> onOpenService;

  @override
  Widget build(BuildContext context) {
    final surface = ComposedSurface(
      surfaceId: 'discovery',
      task: SurfaceTask.discovery,
      fallback: 'discovery',
      components: [
        for (final service in candidates)
          SurfaceComponent(
            type: 'serviceResultRow',
            data: {'service': service.toJson()},
          ),
      ],
    );
    return ComposedTaskSurface(
      surface: surface,
      onServiceSelected: (service) => onOpenService(service.serviceId),
      onFallbackAction: candidates.isEmpty
          ? null
          : () => onOpenService(candidates.first.serviceId),
    );
  }
}

class _Clarification extends ConsumerWidget {
  const _Clarification({
    required this.question,
    required this.candidates,
    required this.onOpenService,
  });

  final String? question;
  final List<ServiceSummary> candidates;
  final ValueChanged<String> onOpenService;

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
                onSelect: () => onOpenService(service.serviceId),
              ),
              const SizedBox(height: SabSpacing.sm),
            ],
          ],
        ],
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
                  style: SabTypography.body.copyWith(
                    color: colors.textPrimary,
                  ),
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
                  decoration: InputDecoration(
                    hintText: strings.composerHint,
                  ),
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
