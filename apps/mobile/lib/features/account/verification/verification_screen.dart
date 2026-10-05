import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../components/offline_banner.dart';
import '../../../core/connectivity.dart';
import '../../../design_system/tokens.dart';
import 'verification_strings.dart';
import 'verification_task_view.dart';

/// Screen 5: Identity Verification (`/account/verify`). Verify identity once
/// against the national identity infrastructure so regulated payments can
/// proceed (FEAT-002; CONTRACTS.md C-020–C-022).
///
/// The ceremony itself lives in [VerificationTaskView], which the conversation
/// also renders inline; this screen is the non-conversation route to the same
/// task, reached from Account. [fromPayment] is true when the surface was opened
/// because a payment is held for KYC. On a match the primary action then returns
/// to the held payment instead of Account, so details are not re-entered
/// (user-flow, Flow 5).
class VerificationScreen extends ConsumerWidget {
  const VerificationScreen({super.key, this.fromPayment = false});

  final bool fromPayment;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(verificationStringsProvider);
    final online = ref.watch(connectivityProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(strings.title),
        leading: BackButton(onPressed: () => _exit(context)),
      ),
      body: Column(
        children: [
          if (!online) OfflineBanner(message: strings.offlineBody),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(SabSpacing.md),
              child: VerificationTaskView(
                fromPayment: fromPayment,
                onExit: () => _exit(context),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _exit(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/account');
    }
  }
}
