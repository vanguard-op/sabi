import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/connectivity.dart';
import '../../data/providers.dart';
import '../../data/repositories.dart';
import '../../models/payment_case.dart';

/// What the case task is doing, so every state has a place and no failure is
/// swallowed. The presentation the user reads (reconciling, waiting on the
/// biller, escalated, resolved) is derived from the case and payment records by
/// [CaseDetail.presentation]; this enum tracks the load and the two actions the
/// conversation and the Case screen both drive (C-026–C-029, FEAT-009).
enum CasePhase {
  loading,
  ready,
  refunding,
  refunded,
  disputing,
  disputed,
  offline,
  error,
}

/// A transient outcome of a refund or dispute. It renders inline as a notice, so
/// the user sees whether the action went through without a screen-level
/// snackbar and the conversation and the screen read the same.
enum CaseNotice {
  refundSubmitted,
  refundBlocked,
  disputeSubmitted,
  disputeBlocked,
  actionFailed,
}

/// The immutable state the case task renders.
@immutable
class CaseState {
  const CaseState({
    this.phase = CasePhase.loading,
    this.detail,
    this.notice,
    this.online = true,
  });

  final CasePhase phase;

  /// The case with its payment and timeline (C-027), once loaded.
  final CaseDetail? detail;

  /// The outcome of the last refund or dispute, if any.
  final CaseNotice? notice;

  final bool online;

  /// The presentation the user reads. A refund that has just been accepted
  /// reads as refund-started even before the record refreshes, so the state the
  /// user was shown and the state they are in agree.
  CasePresentation get presentation {
    if (phase == CasePhase.refunded) return CasePresentation.refundInitiated;
    return detail?.presentation ?? CasePresentation.pending;
  }

  /// True while a refund or dispute is in flight, so the view locks its actions.
  bool get isBusy =>
      phase == CasePhase.refunding || phase == CasePhase.disputing;

  /// A refund may start where the case is reconciling or waiting on the biller,
  /// online, and no action is already in flight. A duplicate is blocked by the
  /// repository and reported, never by hiding the action.
  bool get canRefund =>
      online &&
      !isBusy &&
      phase != CasePhase.refunded &&
      detail != null &&
      (presentation == CasePresentation.reconciling ||
          presentation == CasePresentation.awaitingBiller);

  /// A dispute is raised on an escalated case, online, and not already raised.
  bool get canDispute =>
      online &&
      !isBusy &&
      phase != CasePhase.disputed &&
      detail != null &&
      presentation == CasePresentation.escalated;

  CaseState copyWith({
    CasePhase? phase,
    CaseDetail? detail,
    CaseNotice? notice,
    bool clearNotice = false,
    bool? online,
  }) => CaseState(
    phase: phase ?? this.phase,
    detail: detail ?? this.detail,
    notice: clearNotice ? null : (notice ?? this.notice),
    online: online ?? this.online,
  );
}

/// The state machine for one case (FEAT-009; C-026–C-029). It loads the case,
/// its payment, and its timeline (C-027) and drives the two recovery actions: a
/// refund (C-029) and a dispute (C-028). The conversation renders this inline and
/// the Case screen hosts it, so the inline task and the screen cannot drift.
class CaseController extends Notifier<CaseState> {
  CaseController(this.caseId);

  /// The case this controller owns; the family argument.
  final String caseId;

  bool _online = true;

  @override
  CaseState build() {
    _online = ref.read(connectivityProvider);
    scheduleMicrotask(load);
    return CaseState(online: _online);
  }

  CasesRepository get _repo => ref.read(casesRepositoryProvider);

  /// Loads the case with its payment and timeline (C-027).
  Future<void> load() async {
    state = state.copyWith(phase: CasePhase.loading, clearNotice: true);
    try {
      final detail = await _repo.detail(caseId);
      if (!ref.mounted) return;
      state = state.copyWith(phase: CasePhase.ready, detail: detail);
    } catch (_) {
      if (!ref.mounted) return;
      state = state.copyWith(phase: CasePhase.error);
    }
  }

  /// Requests a refund for the payment under this case (C-029). The idempotency
  /// key makes a retry the same refund, never a second one; a duplicate is
  /// reported plainly rather than silently swallowed.
  Future<void> refund() async {
    final detail = state.detail;
    if (detail == null || !state.canRefund) return;
    if (!_online) {
      state = state.copyWith(phase: CasePhase.offline);
      return;
    }
    state = state.copyWith(phase: CasePhase.refunding, clearNotice: true);
    try {
      await _repo.refund(
        paymentId: detail.payment.paymentId,
        reason: 'Requested by the user',
        idempotencyKey: 'refund_${detail.payment.paymentId}',
      );
      if (!ref.mounted) return;
      state = state.copyWith(
        phase: CasePhase.refunded,
        notice: CaseNotice.refundSubmitted,
      );
      await _refresh();
    } on DuplicateRefundException {
      if (!ref.mounted) return;
      state = state.copyWith(
        phase: CasePhase.refunded,
        notice: CaseNotice.refundBlocked,
      );
    } on RefundNotAllowedException {
      // C-029 422: the payment's current state does not allow a refund. State it
      // plainly so the user knows the recovery is not available here.
      if (!ref.mounted) return;
      state = state.copyWith(
        phase: CasePhase.ready,
        notice: CaseNotice.refundBlocked,
      );
    } catch (_) {
      if (!ref.mounted) return;
      state = state.copyWith(
        phase: CasePhase.ready,
        notice: CaseNotice.actionFailed,
      );
    }
  }

  /// Opens a dispute on the case (C-028). A duplicate is reported plainly.
  Future<void> dispute() async {
    final detail = state.detail;
    if (detail == null || !state.canDispute) return;
    if (!_online) {
      state = state.copyWith(phase: CasePhase.offline);
      return;
    }
    state = state.copyWith(phase: CasePhase.disputing, clearNotice: true);
    try {
      await _repo.dispute(
        caseId: detail.paymentCase.id,
        reason: 'Requested by the user',
      );
      if (!ref.mounted) return;
      state = state.copyWith(
        phase: CasePhase.disputed,
        notice: CaseNotice.disputeSubmitted,
      );
      await _refresh();
    } on DuplicateDisputeException {
      if (!ref.mounted) return;
      state = state.copyWith(
        phase: CasePhase.ready,
        notice: CaseNotice.disputeBlocked,
      );
    } catch (_) {
      if (!ref.mounted) return;
      state = state.copyWith(
        phase: CasePhase.ready,
        notice: CaseNotice.actionFailed,
      );
    }
  }

  /// Refreshes the case record after an action without discarding the outcome
  /// the user was just shown.
  Future<void> _refresh() async {
    try {
      final detail = await _repo.detail(caseId);
      if (!ref.mounted) return;
      state = state.copyWith(detail: detail);
    } catch (_) {
      // The action already succeeded; a refresh failure must not undo it.
    }
  }

  /// Reflects a connectivity change; a load is retried when back online.
  void setOnline(bool online) {
    final wasOffline = !_online;
    _online = online;
    state = state.copyWith(online: online);
    if (online && wasOffline && state.phase == CasePhase.error) {
      load();
    }
  }
}

/// One controller per case, keyed by the case id.
final caseControllerProvider =
    NotifierProvider.family<CaseController, CaseState, String>(
      CaseController.new,
    );
