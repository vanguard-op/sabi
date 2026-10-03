import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/sab_button.dart';
import '../../components/sab_text_field.dart';
import '../../core/passkey/passkey_ceremony.dart';
import '../../data/providers.dart';
import '../../design_system/sab_art.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';

/// Screen 2: Sign In (`/sign-in`). Return to the account with a passkey, or with
/// a recovery code when the only passkey is lost.
class SignInScreen extends ConsumerStatefulWidget {
  const SignInScreen({super.key, this.from});

  final String? from;

  @override
  ConsumerState<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends ConsumerState<SignInScreen> {
  final _codeController = TextEditingController();
  bool _showRecovery = false;
  bool _verifying = false;
  String? _error;

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _signInWithPasskey() async {
    final strings = ref.read(sabStringsProvider);
    setState(() {
      _verifying = true;
      _error = null;
    });
    try {
      await ref.read(authRepositoryProvider).signInWithPasskey();
      if (!mounted) return;
      ref.read(sessionProvider).signIn();
      context.go(widget.from ?? '/home');
    } on PasskeyUnavailable catch (error) {
      if (!mounted) return;
      // No passkey can run here. The relying-party case is a build setup
      // problem, so name it and point at the recovery-code route already on
      // screen instead of the generic rejection copy.
      setState(() {
        _error = error.reason == PasskeyUnavailableReason.domainNotAssociated
            ? strings.passkeySetupUnavailableSignIn
            : strings.passkeyFailed;
      });
    } on PasskeyCeremonyFailure catch (error) {
      if (!mounted) return;
      // A dismissed sheet is a quiet return to ready, not an error.
      if (error.reason != PasskeyFailureReason.cancelled) {
        setState(() => _error = strings.passkeyRetry);
      }
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = strings.passkeyFailed);
    } finally {
      if (mounted) setState(() => _verifying = false);
    }
  }

  Future<void> _signInWithRecovery() async {
    final strings = ref.read(sabStringsProvider);
    if (_codeController.text.trim().isEmpty) {
      setState(() => _error = strings.requiredField);
      return;
    }
    setState(() {
      _verifying = true;
      _error = null;
    });
    try {
      final result = await ref
          .read(authRepositoryProvider)
          .signInWithRecovery(_codeController.text);
      if (!mounted) return;
      if (result.mustEnrolPasskey) {
        await _promptEnrolPasskey();
      }
      if (!mounted) return;
      ref.read(sessionProvider).signIn();
      context.go(widget.from ?? '/home');
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = strings.signInFailed);
    } finally {
      if (mounted) setState(() => _verifying = false);
    }
  }

  Future<void> _promptEnrolPasskey() async {
    final strings = ref.read(sabStringsProvider);
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(strings.enrolPasskeyTitle),
        content: Text(strings.enrolPasskeyBody),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(strings.later),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(strings.enrolPasskeyAction),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(SabSpacing.xl),
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: SabSizes.contentMaxWidth,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Center(
                    child: SabArt(
                      artboard: SabArtboard.brandMark,
                      size: SabSizes.artBrandMarkSmall,
                      semanticLabel: 'Sabi',
                    ),
                  ),
                  const SizedBox(height: SabSpacing.md),
                  Text(
                    strings.signInHeading,
                    textAlign: TextAlign.center,
                    style: SabTypography.h2.copyWith(color: colors.textPrimary),
                  ),
                  const SizedBox(height: SabSpacing.xl),
                  SabButton(
                    label: strings.continueWithPasskey,
                    loading: _verifying && !_showRecovery,
                    onPressed: _verifying ? null : _signInWithPasskey,
                  ),
                  if (_verifying && !_showRecovery) ...[
                    const SizedBox(height: SabSpacing.sm),
                    Text(
                      strings.passkeyPrompt,
                      textAlign: TextAlign.center,
                      style: SabTypography.bodySmall.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  ],
                  const SizedBox(height: SabSpacing.sm),
                  SabButton(
                    label: strings.useRecoveryCode,
                    variant: SabButtonVariant.ghost,
                    onPressed: _verifying
                        ? null
                        : () => setState(() => _showRecovery = !_showRecovery),
                  ),
                  if (_showRecovery) ...[
                    const SizedBox(height: SabSpacing.md),
                    SabTextField(
                      label: strings.recoveryCodeLabel,
                      hint: strings.recoveryCodeHint,
                      controller: _codeController,
                      enabled: !_verifying,
                      errorText: _error,
                      autofocus: true,
                      onSubmitted: (_) => _signInWithRecovery(),
                    ),
                    const SizedBox(height: SabSpacing.md),
                    SabButton(
                      label: strings.submitRecovery,
                      loading: _verifying,
                      expand: true,
                      onPressed: _verifying ? null : _signInWithRecovery,
                    ),
                  ] else if (_error != null) ...[
                    const SizedBox(height: SabSpacing.md),
                    Text(
                      _error!,
                      textAlign: TextAlign.center,
                      style: SabTypography.bodySmall.copyWith(
                        color: colors.error500,
                      ),
                    ),
                  ],
                  const SizedBox(height: SabSpacing.lg),
                  SabButton(
                    label: strings.createAccount,
                    variant: SabButtonVariant.ghost,
                    onPressed: _verifying ? null : () => context.go('/welcome'),
                  ),
                  const SizedBox(height: SabSpacing.lg),
                  Text(
                    strings.unrecoverable,
                    textAlign: TextAlign.center,
                    style: SabTypography.caption.copyWith(
                      color: colors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
