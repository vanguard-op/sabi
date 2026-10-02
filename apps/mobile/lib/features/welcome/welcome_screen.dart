import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/offline_banner.dart';
import '../../components/recovery_code_sheet.dart';
import '../../components/sab_button.dart';
import '../../core/connectivity.dart';
import '../../data/providers.dart';
import '../../data/repositories.dart';
import '../../design_system/sab_art.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';

/// Screen 1: Welcome (`/welcome`). Create an account with a passkey, or sign in,
/// without a phone number or password.
class WelcomeScreen extends ConsumerStatefulWidget {
  const WelcomeScreen({super.key, this.from});

  /// The protected route to return to after authentication, from a deep link.
  final String? from;

  @override
  ConsumerState<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends ConsumerState<WelcomeScreen> {
  bool _checking = true;
  bool _passkeySupported = true;
  bool _creating = false;
  bool _queued = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _checkCapability();
  }

  Future<void> _checkCapability() async {
    try {
      final supported = await ref
          .read(authRepositoryProvider)
          .passkeySupported();
      if (!mounted) return;
      setState(() {
        _passkeySupported = supported;
        _checking = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _checking = false;
        _error = ref.read(sabStringsProvider).errorGeneric;
      });
    }
  }

  Future<void> _getStarted() async {
    final strings = ref.read(sabStringsProvider);
    if (!ref.read(connectivityProvider)) {
      setState(() => _queued = true);
      return;
    }
    setState(() {
      _creating = true;
      _error = null;
    });
    final RegistrationResult result;
    try {
      result = await ref
          .read(authRepositoryProvider)
          .createAccount(
            locale: ref.read(localeProvider),
            withPasskey: _passkeySupported,
          );
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _creating = false;
        _error = strings.createFailed;
      });
      return;
    }
    if (!mounted) return;
    // Stop the action spinner before the blocking sheet appears.
    setState(() => _creating = false);
    final acknowledged = await showSabRecoveryCodeSheet(
      context,
      code: result.recoveryCode,
    );
    if (!mounted) return;
    if (acknowledged) {
      ref.read(sessionProvider).signIn();
      context.go(widget.from ?? '/home');
    }
  }

  void _showDataHandling() {
    final strings = ref.read(sabStringsProvider);
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(strings.dataHandling),
        content: Text(strings.dataHandlingBody),
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
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    final online = ref.watch(connectivityProvider);

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            if (!online)
              OfflineBanner(
                message: strings.offlineQueue,
                queuedLabel: _queued ? strings.queuedOffline : null,
              ),
            Expanded(
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(SabSpacing.xl),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(
                      maxWidth: SabSizes.contentMaxWidth,
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const SabArt(
                          artboard: SabArtboard.brandMark,
                          size: SabSizes.artBrandMark,
                          semanticLabel: 'Sabi',
                        ),
                        const SizedBox(height: SabSpacing.lg),
                        Text(
                          strings.tagline,
                          textAlign: TextAlign.center,
                          style: SabTypography.h1.copyWith(
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: SabSpacing.sm),
                        Text(
                          strings.welcomeValue,
                          textAlign: TextAlign.center,
                          style: SabTypography.bodyLarge.copyWith(
                            color: colors.textSecondary,
                          ),
                        ),
                        if (!_passkeySupported && !_checking) ...[
                          const SizedBox(height: SabSpacing.lg),
                          _UnsupportedCallout(
                            title: strings.passkeyUnsupportedTitle,
                            body: strings.passkeyUnsupportedBody,
                          ),
                        ],
                        if (_error != null) ...[
                          const SizedBox(height: SabSpacing.lg),
                          Text(
                            _error!,
                            textAlign: TextAlign.center,
                            style: SabTypography.bodySmall.copyWith(
                              color: colors.error500,
                            ),
                          ),
                        ],
                        const SizedBox(height: SabSpacing.xl),
                        SabButton(
                          label: _passkeySupported
                              ? strings.getStarted
                              : strings.useRecoveryInstead,
                          loading: _checking || _creating,
                          expand: true,
                          onPressed: _checking ? null : _getStarted,
                        ),
                        const SizedBox(height: SabSpacing.sm),
                        SabButton(
                          label: strings.signIn,
                          variant: SabButtonVariant.ghost,
                          onPressed: () => context.go('/sign-in'),
                        ),
                        const SizedBox(height: SabSpacing.xs),
                        SabButton(
                          label: strings.dataHandling,
                          variant: SabButtonVariant.ghost,
                          onPressed: _showDataHandling,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _UnsupportedCallout extends StatelessWidget {
  const _UnsupportedCallout({required this.title, required this.body});

  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
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
            title,
            style: SabTypography.body.copyWith(
              color: colors.warning900,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: SabSpacing.xs),
          Text(
            body,
            style: SabTypography.bodySmall.copyWith(color: colors.warning900),
          ),
        ],
      ),
    );
  }
}
