import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../components/empty_state.dart';
import '../../components/error_state.dart';
import '../../components/offline_banner.dart';
import '../../components/receipt_card.dart';
import '../../components/sab_button.dart';
import '../../components/sab_text_field.dart';
import '../../components/skeleton.dart';
import '../../core/connectivity.dart';
import '../../core/money.dart';
import '../../design_system/icons.dart';
import '../../design_system/tokens.dart';
import '../../l10n/sab_strings.dart';
import 'receipts_controller.dart';

/// Screen 6: Receipts (`/receipts`), in the navigation shell. A search field is
/// pinned below the AppBar and the body is a month-grouped list of Receipt
/// Cards, newest first. Every state from screens/06-receipts.md is covered:
/// loading, empty, loaded, searching, no results, error, and offline.
class ReceiptsScreen extends ConsumerStatefulWidget {
  const ReceiptsScreen({super.key});

  @override
  ConsumerState<ReceiptsScreen> createState() => _ReceiptsScreenState();
}

class _ReceiptsScreenState extends ConsumerState<ReceiptsScreen> {
  final _searchController = TextEditingController();
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  /// Searches after a short pause so a query in progress replaces the list once
  /// rather than thrashing on every keystroke.
  void _onQueryChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      ref.read(receiptsControllerProvider.notifier).search(value);
    });
  }

  void _clearSearch() {
    _searchController.clear();
    _debounce?.cancel();
    ref.read(receiptsControllerProvider.notifier).search('');
  }

  @override
  Widget build(BuildContext context) {
    final strings = ref.watch(sabStringsProvider);
    final online = ref.watch(connectivityProvider);
    final state = ref.watch(receiptsControllerProvider);

    return Scaffold(
      appBar: AppBar(title: Text(strings.receiptsTitle)),
      body: Column(
        children: [
          if (!online) OfflineBanner(message: strings.offlineReceipts),
          Padding(
            padding: const EdgeInsets.fromLTRB(
              SabSpacing.md,
              SabSpacing.md,
              SabSpacing.md,
              SabSpacing.sm,
            ),
            child: SabTextField(
              controller: _searchController,
              label: strings.searchReceiptsLabel,
              hint: strings.searchReceiptsHint,
              textInputAction: TextInputAction.search,
              onChanged: _onQueryChanged,
              onSubmitted: (value) {
                _debounce?.cancel();
                ref.read(receiptsControllerProvider.notifier).search(value);
              },
              suffixIcon: state.query.isEmpty
                  ? null
                  : IconButton(
                      tooltip: strings.clearSearch,
                      onPressed: _clearSearch,
                      icon: const SabIconView(SabIcons.close),
                    ),
            ),
          ),
          Expanded(child: _body(state, strings, online)),
        ],
      ),
    );
  }

  Widget _body(ReceiptsState state, SabStrings strings, bool online) {
    if (state.isInitialLoading) {
      return const Padding(
        padding: EdgeInsets.all(SabSpacing.md),
        child: SabSkeletonList(),
      );
    }
    if (state.error && state.receipts.isEmpty) {
      return ErrorState(
        message: strings.homeLoadError,
        retryLabel: strings.retry,
        onRetry: () => ref.read(receiptsControllerProvider.notifier).retry(),
      );
    }
    if (state.isEmpty) {
      return EmptyState(
        title: strings.receiptsEmptyTitle,
        message: strings.receiptsEmptyBody,
        actionLabel: strings.receiptsEmptyAction,
        onAction: () {
          ref.read(receiptsControllerProvider.notifier).retry();
        },
        semanticLabel: strings.receiptsEmptyTitle,
      );
    }
    if (state.hasNoResults) {
      return _NoResults(query: state.query, onClear: _clearSearch);
    }
    return _ReceiptList(
      state: state,
      strings: strings,
      onLoadMore: () =>
          ref.read(receiptsControllerProvider.notifier).loadMore(),
    );
  }
}

/// The no-results state: names the query and offers a way to clear it.
class _NoResults extends ConsumerWidget {
  const _NoResults({required this.query, required this.onClear});

  final String query;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    return EmptyState(
      title: strings.noResultsTitle,
      message: SabStrings.fill(strings.noResultsBody, {'query': query}),
      actionLabel: strings.clearSearch,
      onAction: onClear,
      semanticLabel: strings.noResultsTitle,
    );
  }
}

/// The grouped list: a month header before each month's receipts, newest
/// first, with a non-blocking pager at the end.
class _ReceiptList extends ConsumerWidget {
  const _ReceiptList({
    required this.state,
    required this.strings,
    required this.onLoadMore,
  });

  final ReceiptsState state;
  final SabStrings strings;
  final VoidCallback onLoadMore;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final months = state.months;
    final itemCount = months.length + (state.nextCursor != null ? 1 : 0);

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(
        SabSpacing.md,
        SabSpacing.sm,
        SabSpacing.md,
        SabSpacing.xl,
      ),
      itemCount: itemCount,
      itemBuilder: (context, index) {
        if (index == months.length) {
          return Padding(
            padding: const EdgeInsets.only(top: SabSpacing.sm),
            child: SabButton(
              label: strings.loadMore,
              variant: SabButtonVariant.outline,
              expand: true,
              loading: state.loadingMore,
              onPressed: state.loadingMore ? null : onLoadMore,
            ),
          );
        }
        final month = months[index];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: EdgeInsets.only(
                top: index == 0 ? 0 : SabSpacing.md,
                bottom: SabSpacing.sm,
              ),
              child: Text(
                SabMoney.formatMonth(month.month, locale: ref.watch(localeProvider).code),
                style: SabTypography.caption.copyWith(
                  color: colors.textSecondary,
                ),
              ),
            ),
            for (final receipt in month.receipts)
              Padding(
                padding: const EdgeInsets.only(bottom: SabSpacing.md),
                child: ReceiptCard(
                  receipt: receipt,
                  onTap: () => context.push('/receipts/${receipt.id}'),
                ),
              ),
          ],
        );
      },
    );
  }
}
