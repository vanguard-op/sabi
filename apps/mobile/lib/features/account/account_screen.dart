import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/error_state.dart';
import '../../components/offline_banner.dart';
import '../../components/sab_button.dart';
import '../../components/sab_text_field.dart';
import '../../components/section_card.dart';
import '../../components/skeleton.dart';
import '../../components/status_pill.dart';
import '../../core/connectivity.dart';
import '../../data/providers.dart';
import '../../data/repositories.dart';
import '../../design_system/icons.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import '../../models/account.dart';
import '../../models/channel_link.dart';
import '../../models/payment_method.dart';

final accountProvider = FutureProvider<Account>(
  (ref) => ref.watch(accountRepositoryProvider).me(),
);

final paymentMethodsProvider = FutureProvider<List<PaymentMethod>>(
  (ref) => ref.watch(accountRepositoryProvider).paymentMethods(),
);

/// Screen 9: Account (`/account`). Identity, linked channels, payment methods,
/// and verification and account status.
class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final online = ref.watch(connectivityProvider);
    final account = ref.watch(accountProvider);
    final methods = ref.watch(paymentMethodsProvider);

    return Scaffold(
      appBar: AppBar(title: Text(strings.accountTitle)),
      body: Column(
        children: [
          if (!online) OfflineBanner(message: strings.offlineAccount),
          Expanded(
            child: account.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(SabSpacing.md),
                child: SabSkeletonList(rows: 3),
              ),
              error: (_, _) => ErrorState(
                message: strings.loadError,
                retryLabel: strings.retry,
                onRetry: () => ref.invalidate(accountProvider),
              ),
              data: (value) => _AccountBody(
                account: value,
                methods: methods,
                strings: strings,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _AccountBody extends ConsumerWidget {
  const _AccountBody({
    required this.account,
    required this.methods,
    required this.strings,
  });

  final Account account;
  final AsyncValue<List<PaymentMethod>> methods;
  final SabStrings strings;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final suspended = account.isSuspended;
    return ListView(
      padding: const EdgeInsets.all(SabSpacing.md),
      children: [
        if (strings.hasFallback) ...[
          _FallbackNote(text: strings.fallbackNote),
          const SizedBox(height: SabSpacing.md),
        ],
        SectionCard(
          title: strings.profileGroup,
          children: [
            SectionRow(
              label: strings.displayName,
              value: account.displayName ?? strings.displayNameUnset,
            ),
            SectionRow(
              label: strings.localeLabel,
              value: '',
              icon: SabIcons.language,
              valueWidget: DropdownButton<AppLocale>(
                value: ref.watch(localeProvider),
                underline: const SizedBox.shrink(),
                borderRadius: BorderRadius.circular(SabRadii.md),
                onChanged: (value) {
                  if (value == null) return;
                  ref.read(localeProvider.notifier).set(value);
                  ref.read(accountRepositoryProvider).updateLocale(value);
                },
                items: [
                  for (final locale in AppLocale.values)
                    DropdownMenuItem(
                      value: locale,
                      child: Text(
                        locale.nativeLabel,
                        style: SabTypography.bodySmall.copyWith(
                          color: colors.textPrimary,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: SabSpacing.md),
        SectionCard(
          title: strings.verificationGroup,
          trailing: StatusPill(status: _verificationStatus(account)),
          children: [
            const SizedBox(height: SabSpacing.xs),
            Text(
              _verificationMessage(account),
              style: SabTypography.bodySmall.copyWith(
                color: suspended ? colors.error500 : colors.textSecondary,
              ),
            ),
            if (account.kycStatus == VerificationStatus.unverified &&
                !suspended) ...[
              const SizedBox(height: SabSpacing.md),
              SabButton(
                label: strings.verifyIdentity,
                expand: true,
                onPressed: () => context.push('/account/verify'),
              ),
            ],
          ],
        ),
        const SizedBox(height: SabSpacing.md),
        SectionCard(
          title: strings.channelsGroup,
          children: [
            for (final channel in const ['ussd', 'sms', 'whatsapp'])
              _ChannelRow(
                label: switch (channel) {
                  'ussd' => strings.channelUssd,
                  'sms' => strings.channelSms,
                  _ => strings.channelWhatsapp,
                },
                channel: channel,
                link: account.channelLinks
                    .where((l) => l.channel == channel)
                    .firstOrNull,
              ),
          ],
        ),
        const SizedBox(height: SabSpacing.md),
        SectionCard(
          title: strings.methodsGroup,
          children: [
            if (suspended)
              Text(
                strings.suspendedReason,
                style: SabTypography.bodySmall.copyWith(color: colors.error500),
              )
            else
              methods.when(
                loading: () => const SabSkeleton(height: SabSizes.inputHeight),
                error: (_, _) => Text(
                  strings.loadError,
                  style: SabTypography.bodySmall.copyWith(
                    color: colors.textSecondary,
                  ),
                ),
                data: (items) => items.isEmpty
                    ? Text(
                        strings.noMethods,
                        style: SabTypography.bodySmall.copyWith(
                          color: colors.textSecondary,
                        ),
                      )
                    : Column(
                        children: [
                          for (final method in items)
                            SectionRow(
                              label: method.label,
                              value: strings.methodSaved,
                              icon: SabIcons.paymentMethod,
                            ),
                        ],
                      ),
              ),
          ],
        ),
        const SizedBox(height: SabSpacing.lg),
        SabButton(
          label: strings.signOut,
          variant: SabButtonVariant.ghost,
          icon: SabIcons.signOut,
          onPressed: () async {
            await ref.read(authRepositoryProvider).signOut();
            ref.read(sessionProvider).signOut();
            if (context.mounted) context.go('/welcome');
          },
        ),
      ],
    );
  }

  SabStatus _verificationStatus(Account account) {
    if (account.isSuspended) return SabStatus.suspended;
    return switch (account.kycStatus) {
      VerificationStatus.verified => SabStatus.verified,
      VerificationStatus.pending => SabStatus.pending,
      _ => SabStatus.unverified,
    };
  }

  String _verificationMessage(Account account) {
    if (account.isSuspended) return strings.suspendedReason;
    return switch (account.kycStatus) {
      VerificationStatus.verified => strings.verificationVerified,
      VerificationStatus.pending => strings.verificationPending,
      _ => strings.verificationUnverified,
    };
  }
}

class _ChannelRow extends ConsumerWidget {
  const _ChannelRow({required this.label, required this.channel, this.link});

  final String label;
  final String channel;
  final ChannelLink? link;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    return SectionRow(
      label: label,
      value: link?.address ?? strings.channelNotLinked,
      valueWidget: link != null
          ? Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  link!.address,
                  style: SabTypography.bodySmall.copyWith(
                    color: colors.textSecondary,
                  ),
                ),
                const SizedBox(width: SabSpacing.sm),
                if (link!.isVerified)
                  const StatusPill(status: SabStatus.verified, label: 'Linked'),
              ],
            )
          : SabButton(
              label: strings.linkChannel,
              variant: SabButtonVariant.ghost,
              onPressed: () => _link(context, ref),
            ),
    );
  }

  Future<void> _link(BuildContext context, WidgetRef ref) async {
    final strings = ref.read(sabStringsProvider);
    final address = await showDialog<String>(
      context: context,
      builder: (context) => _LinkChannelDialog(title: strings.linkChannelTitle),
    );
    if (address == null || address.trim().isEmpty) return;
    try {
      await ref
          .read(accountRepositoryProvider)
          .linkChannel(channel: channel, address: address);
      ref.invalidate(accountProvider);
    } on ChannelAlreadyLinkedException {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(strings.channelAlreadyLinked)));
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(strings.channelLinkFailed)));
    }
  }
}

class _LinkChannelDialog extends ConsumerStatefulWidget {
  const _LinkChannelDialog({required this.title});

  final String title;

  @override
  ConsumerState<_LinkChannelDialog> createState() => _LinkChannelDialogState();
}

class _LinkChannelDialogState extends ConsumerState<_LinkChannelDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = ref.watch(sabStringsProvider);
    return AlertDialog(
      title: Text(widget.title),
      content: SabTextField(
        label: strings.channelAddressLabel,
        controller: _controller,
        keyboardType: TextInputType.phone,
        autofocus: true,
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(strings.cancel),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(_controller.text),
          child: Text(strings.continueLabel),
        ),
      ],
    );
  }
}

class _FallbackNote extends ConsumerWidget {
  const _FallbackNote({required this.text});

  final String text;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    return Container(
      padding: const EdgeInsets.all(SabSpacing.sm),
      decoration: BoxDecoration(
        color: colors.info100,
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
      child: Row(
        children: [
          SabIconView(
            SabIcons.info,
            size: SabSizes.iconSm,
            color: colors.info900,
          ),
          const SizedBox(width: SabSpacing.sm),
          Expanded(
            child: Text(
              text,
              style: SabTypography.caption.copyWith(color: colors.info900),
            ),
          ),
        ],
      ),
    );
  }
}
