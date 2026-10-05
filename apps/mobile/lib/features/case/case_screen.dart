import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/offline_banner.dart';
import '../../core/connectivity.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import 'case_task_view.dart';

/// Screen 8: Case (`/cases/:caseId`). Shows the true state of a failed or
/// reversed payment and drives a refund or reconciliation to a resolution.
///
/// The task itself lives in [CaseTaskView], which the conversation also renders
/// inline (FEAT-011); this screen is the non-conversation route to the same
/// task, reached from Receipt Detail. The recovery controller it drives is the
/// same state machine, so the conversation is the primary path and the screen
/// stays a fully functional alternate route (D-057).
class CaseScreen extends ConsumerWidget {
  const CaseScreen({super.key, required this.caseId});

  final String caseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final online = ref.watch(connectivityProvider);

    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.pop()),
        title: Text(strings.caseTitle),
      ),
      body: Column(
        children: [
          if (!online) OfflineBanner(message: strings.caseOffline),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(SabSpacing.md),
              child: CaseTaskView(caseId: caseId),
            ),
          ),
        ],
      ),
    );
  }
}
