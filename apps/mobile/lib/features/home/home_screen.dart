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
import '../../models/intent_result.dart';
import '../../models/receipt_summary.dart';
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
    final intent = await controller.submit(text);
    if (!mounted || intent == null) return;
    final candidates = intent.candidates;
    if (candidates.length > 1) {
      final chosen = await showSabProviderPickerSheet(
        context,
        candidates: candidates,
      );
      if (chosen != null && mounted) _openService(chosen.serviceId);
    } else if (candidates.isNotEmpty) {
      _openService(candidates.first.serviceId);
    }
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
                onRetry: () =>
                    ref.read(homeControllerProvider.notifier).retry(),
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
  });

  final List<ReceiptSummary> receipts;
  final HomeState state;
  final ValueChanged<String> onOpenService;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    final showEmpty = receipts.isEmpty && state.phase == HomePhase.idle;

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
        _Interaction(
          state: state,
          onOpenService: onOpenService,
          onRetry: onRetry,
        ),
      ],
    );
  }
}

class _Interaction extends ConsumerWidget {
  const _Interaction({
    required this.state,
    required this.onOpenService,
    required this.onRetry,
  });

  final HomeState state;
  final ValueChanged<String> onOpenService;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    switch (state.phase) {
      case HomePhase.idle:
        if (!state.queued) return const SizedBox.shrink();
        return _Notice(
          title: strings.queuedOffline,
          body: strings.offlineNoPayment,
        );
      case HomePhase.composing:
        return Container(
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
                style: SabTypography.body.copyWith(color: colors.textSecondary),
              ),
            ],
          ),
        );
      case HomePhase.discovery:
        return ComposedTaskSurface(
          surface: _discoverySurface(state.intent!),
          onServiceSelected: (service) => onOpenService(service.serviceId),
          onFallbackAction: () =>
              onOpenService(state.intent!.candidates.first.serviceId),
        );
      case HomePhase.clarifying:
        return _Clarification(
          intent: state.intent!,
          onOpenService: onOpenService,
        );
      case HomePhase.notCovered:
        return _Notice(
          title: strings.notCoveredTitle,
          body: strings.notCoveredBody,
          actionLabel: strings.contactSupport,
          onAction: () {},
        );
      case HomePhase.error:
        return _Notice(
          title: strings.somethingWrong,
          body: strings.sendFailed,
          actionLabel: strings.retry,
          onAction: onRetry,
        );
    }
  }

  ComposedSurface _discoverySurface(IntentResult intent) => ComposedSurface(
    surfaceId: 'discovery',
    task: SurfaceTask.discovery,
    fallback: 'discovery',
    components: [
      for (final service in intent.candidates)
        SurfaceComponent(
          type: 'serviceResultRow',
          data: {'service': service.toJson()},
        ),
    ],
  );
}

class _Clarification extends ConsumerWidget {
  const _Clarification({required this.intent, required this.onOpenService});

  final IntentResult intent;
  final ValueChanged<String> onOpenService;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    final question = intent.clarifyingQuestion;
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
              question,
              style: SabTypography.body.copyWith(color: colors.info900),
            ),
          ],
          const SizedBox(height: SabSpacing.md),
          Text(
            strings.candidates.toUpperCase(),
            style: SabTypography.caption.copyWith(color: colors.info900),
          ),
          const SizedBox(height: SabSpacing.sm),
          for (final service in intent.candidates) ...[
            ServiceResultRow(
              service: service,
              onSelect: () => onOpenService(service.serviceId),
            ),
            const SizedBox(height: SabSpacing.sm),
          ],
        ],
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
              child: TextField(
                controller: controller,
                focusNode: focusNode,
                enabled: enabled,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSend(),
                decoration: InputDecoration(hintText: strings.composerHint),
              ),
            ),
            const SizedBox(width: SabSpacing.sm),
            Semantics(
              button: true,
              label: strings.send,
              child: SizedBox(
                width: SabSizes.minTouchTarget,
                height: SabSizes.minTouchTarget,
                child: IconButton(
                  onPressed: enabled ? onSend : null,
                  icon: const SabIconView(SabIcons.send),
                  color: colors.primary500,
                  tooltip: strings.send,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
