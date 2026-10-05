import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/providers.dart';
import '../../models/receipt.dart';
import '../../models/receipt_summary.dart';

/// A month of receipts, keyed by the first day of the month, newest first
/// (screen 6: "a List of Receipt Cards, newest first, grouped by month").
@immutable
class ReceiptMonth {
  const ReceiptMonth({required this.month, required this.receipts});

  /// Local first-of-month for the group header.
  final DateTime month;
  final List<ReceiptSummary> receipts;
}

/// The Receipts list state. The active query is held separately from results so
/// a pending search can show the previous results rather than flashing empty.
@immutable
class ReceiptsState {
  const ReceiptsState({
    this.receipts = const [],
    this.query = '',
    this.loading = true,
    this.searching = false,
    this.loadingMore = false,
    this.error = false,
    this.nextCursor,
  });

  final List<ReceiptSummary> receipts;
  final String query;
  final bool loading;
  final bool searching;
  final bool loadingMore;
  final bool error;
  final String? nextCursor;

  /// True while the first page is in flight.
  bool get isInitialLoading => loading && receipts.isEmpty;

  /// True once the first page settled with nothing to show.
  bool get isEmpty => !loading && !error && receipts.isEmpty && query.isEmpty;

  /// True when a search completed and matched nothing.
  bool get hasNoResults =>
      !searching && !loading && receipts.isEmpty && query.isNotEmpty;

  /// Groups the loaded receipts by month, newest month and newest receipt
  /// first. Relies on the server's newest-first order.
  List<ReceiptMonth> get months {
    final grouped = <DateTime, List<ReceiptSummary>>{};
    for (final receipt in receipts) {
      final local = receipt.issuedAt.toLocal();
      final key = DateTime(local.year, local.month);
      grouped.putIfAbsent(key, () => []).add(receipt);
    }
    final keys = grouped.keys.toList()..sort((a, b) => b.compareTo(a));
    return [
      for (final key in keys)
        ReceiptMonth(month: key, receipts: grouped[key]!),
    ];
  }

  ReceiptsState copyWith({
    List<ReceiptSummary>? receipts,
    String? query,
    bool? loading,
    bool? searching,
    bool? loadingMore,
    bool? error,
    String? nextCursor,
    bool clearCursor = false,
  }) => ReceiptsState(
    receipts: receipts ?? this.receipts,
    query: query ?? this.query,
    loading: loading ?? this.loading,
    searching: searching ?? this.searching,
    loadingMore: loadingMore ?? this.loadingMore,
    error: error ?? this.error,
    nextCursor: clearCursor ? null : (nextCursor ?? this.nextCursor),
  );
}

/// Drives Receipts (FEAT-008; C-023): first load, search by reference, agency,
/// or date, and cursor pagination. Every request is scoped to the owner by the
/// repository; this controller only shapes the view state.
class ReceiptsController extends Notifier<ReceiptsState> {
  static const _pageSize = 20;

  /// Monotonic id for the newest first-page/search request. A response whose id
  /// is no longer current is discarded, so a slow earlier query can never
  /// overwrite a newer one.
  int _requestId = 0;

  @override
  ReceiptsState build() {
    Future.microtask(_loadFirstPage);
    return const ReceiptsState();
  }

  Future<void> _loadFirstPage() async {
    final id = ++_requestId;
    state = state.copyWith(loading: true, error: false, clearCursor: true);
    try {
      final page = await ref
          .read(receiptsRepositoryProvider)
          .list(query: state.query, limit: _pageSize);
      if (id != _requestId) return;
      state = state.copyWith(
        receipts: page.receipts,
        loading: false,
        searching: false,
        nextCursor: page.nextCursor,
        clearCursor: page.nextCursor == null,
      );
    } catch (_) {
      if (id != _requestId) return;
      state = state.copyWith(loading: false, searching: false, error: true);
    }
  }

  /// Applies a search query and reloads. An emptied query restores the full
  /// list.
  Future<void> search(String query) async {
    final trimmed = query.trim();
    if (trimmed == state.query) return;
    final id = ++_requestId;
    state = state.copyWith(query: trimmed, searching: true, error: false);
    try {
      final page = await ref
          .read(receiptsRepositoryProvider)
          .list(query: trimmed, limit: _pageSize);
      if (id != _requestId) return;
      state = state.copyWith(
        receipts: page.receipts,
        searching: false,
        loading: false,
        nextCursor: page.nextCursor,
        clearCursor: page.nextCursor == null,
      );
    } catch (_) {
      if (id != _requestId) return;
      state = state.copyWith(searching: false, error: true);
    }
  }

  /// Appends the next page without blocking the loaded list.
  Future<void> loadMore() async {
    final cursor = state.nextCursor;
    if (cursor == null || state.loadingMore) return;
    state = state.copyWith(loadingMore: true);
    try {
      final page = await ref
          .read(receiptsRepositoryProvider)
          .list(query: state.query, cursor: cursor, limit: _pageSize);
      state = state.copyWith(
        receipts: [...state.receipts, ...page.receipts],
        loadingMore: false,
        nextCursor: page.nextCursor,
        clearCursor: page.nextCursor == null,
      );
    } catch (_) {
      state = state.copyWith(loadingMore: false);
    }
  }

  /// Retries after a failure, keeping the active query.
  Future<void> retry() => _loadFirstPage();
}

final receiptsControllerProvider =
    NotifierProvider<ReceiptsController, ReceiptsState>(
      ReceiptsController.new,
    );

/// One receipt with its payment (C-024), for the detail screen.
final receiptDetailProvider = FutureProvider.family<ReceiptDetail, String>(
  (ref, receiptId) => ref.watch(receiptsRepositoryProvider).detail(receiptId),
);
