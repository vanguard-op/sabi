import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/empty_state.dart';
import '../../components/error_state.dart';
import '../../components/offline_banner.dart';
import '../../components/receipt_card.dart';
import '../../components/skeleton.dart';
import '../../core/connectivity.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import '../home/home_controller.dart';

/// Screen 6: Receipts (`/receipts`), in the navigation shell. The foundation
/// build lists recent receipts through the shared Receipt Card and empty state;
/// the owning receipts task replaces the stub list with the full spec.
class ReceiptsScreen extends ConsumerWidget {
  const ReceiptsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final online = ref.watch(connectivityProvider);
    final receipts = ref.watch(recentReceiptsProvider);
    return Scaffold(
      appBar: AppBar(title: Text(strings.receiptsTitle)),
      body: Column(
        children: [
          if (!online) OfflineBanner(message: strings.offlineReceipts),
          Expanded(
            child: receipts.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(SabSpacing.md),
                child: SabSkeletonList(),
              ),
              error: (_, _) => ErrorState(
                message: strings.homeLoadError,
                retryLabel: strings.retry,
                onRetry: () => ref.invalidate(recentReceiptsProvider),
              ),
              data: (items) {
                if (items.isEmpty) {
                  return EmptyState(
                    title: strings.receiptsEmptyTitle,
                    message: strings.receiptsEmptyBody,
                    semanticLabel: strings.receiptsEmptyTitle,
                  );
                }
                return ListView.separated(
                  padding: const EdgeInsets.all(SabSpacing.md),
                  itemCount: items.length,
                  separatorBuilder: (_, _) =>
                      const SizedBox(height: SabSpacing.md),
                  itemBuilder: (context, index) {
                    final receipt = items[index];
                    return ReceiptCard(
                      receipt: receipt,
                      onTap: () => context.push('/receipts/${receipt.id}'),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
