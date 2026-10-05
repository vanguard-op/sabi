import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_providers.dart';
import '../../../core/connectivity.dart';
import 'http_verification_repository.dart';
import 'verification_mock.dart';
import 'verification_models.dart';
import 'verification_repository.dart';

/// The repository the screen talks to. The mock is the default so the demo
/// build and the widget tests never open a socket; the `USE_LIVE_REPOSITORIES`
/// build flag selects the HTTP implementation against the gateway, exactly as
/// the other repository providers select live versus mock.
final verificationRepositoryProvider = Provider<VerificationRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpVerificationRepository(ref.watch(apiClientProvider));
  }
  return MockVerificationRepository();
});

/// The screen's state machine (screens/05, "States").
enum VerificationPhase {
  /// Reading the current account status (C-022).
  loading,

  /// The status is known and the user may act.
  ready,

  /// A submission is in flight or being polled (C-020 → C-021).
  checking,

  /// A match returned; no further action.
  verified,

  /// No identity match; one correction attempt may remain.
  noMatch,

  /// The provider is unavailable; the check is queued and the account pending.
  pendingProvider,

  /// Verification rejected or the account suspended; route to support.
  rejected,

  /// A load or submit call failed with a retry.
  error,
}

@immutable
class VerificationState {
  const VerificationState({
    this.phase = VerificationPhase.loading,
    this.status,
    this.correctionUsed = false,
    this.reason,
    this.identifierError,
    this.submitting = false,
    this.online = true,
  });

  final VerificationPhase phase;

  /// The account verification view (C-022).
  final AccountVerification? status;

  /// True once a failed correction has been spent, so the form is no longer
  /// offered (FEAT-002: "allow correction once, then require support").
  final bool correctionUsed;

  /// A plain-language reason from the provider (C-021 `reason`).
  final String? reason;

  /// Field-level validation error for the identifier.
  final String? identifierError;

  /// Distinguishes an in-flight submit from a passive check.
  final bool submitting;

  final bool online;

  /// Whether the user may submit the form at this point.
  bool get canSubmit =>
      online &&
      !submitting &&
      phase != VerificationPhase.checking &&
      phase != VerificationPhase.verified &&
      phase != VerificationPhase.rejected;

  /// Whether a correction attempt is still available after a no-match.
  bool get canCorrect =>
      phase == VerificationPhase.noMatch &&
      status?.canCorrect == true &&
      !correctionUsed;

  VerificationState copyWith({
    VerificationPhase? phase,
    AccountVerification? status,
    bool? correctionUsed,
    String? reason,
    bool clearReason = false,
    String? identifierError,
    bool clearIdentifierError = false,
    bool? submitting,
    bool? online,
  }) {
    return VerificationState(
      phase: phase ?? this.phase,
      status: status ?? this.status,
      correctionUsed: correctionUsed ?? this.correctionUsed,
      reason: clearReason ? null : (reason ?? this.reason),
      identifierError: clearIdentifierError
          ? null
          : (identifierError ?? this.identifierError),
      submitting: submitting ?? this.submitting,
      online: online ?? this.online,
    );
  }
}

class VerificationController extends Notifier<VerificationState> {
  @override
  VerificationState build() {
    _online = ref.read(connectivityProvider);
    scheduleMicrotask(load);
    return VerificationState(online: _online);
  }

  late bool _online;

  VerificationRepository get _repo => ref.read(verificationRepositoryProvider);

  /// Reads the current account verification status (C-022).
  Future<void> load() async {
    state = state.copyWith(phase: VerificationPhase.loading, clearReason: true);
    try {
      final status = await _repo.status();
      state = _stateFor(status);
    } catch (_) {
      state = state.copyWith(phase: VerificationPhase.error);
    }
  }

  /// Submits the identifier and polls the provider to completion (C-020/C-021).
  Future<void> submit({
    required VerificationMethod method,
    required String identifier,
  }) async {
    final trimmed = identifier.trim();
    if (trimmed.isEmpty) {
      state = state.copyWith(identifierError: 'required');
      return;
    }
    if (!_online) return;

    state = state.copyWith(
      phase: VerificationPhase.checking,
      submitting: true,
      clearIdentifierError: true,
      clearReason: true,
    );

    try {
      final submission = await _repo.submit(
        method: method,
        identifier: trimmed,
      );
      if (submission.status == SubmissionStatus.pending) {
        // The provider accepted but has not decided: poll until it does.
        final record = await _repo.check(submission.verificationId);
        state = _stateForRecord(record);
        return;
      }
      // A synchronous decision: read the authoritative account status and map
      // the submission outcome onto the screen phase without spending the
      // correction — only an explicit "correct" tap spends it.
      final status = await _repo.status();
      state = _stateFor(status, submissionStatus: submission.status);
    } on InvalidIdentifierException {
      state = state.copyWith(
        phase: VerificationPhase.ready,
        submitting: false,
        identifierError: 'invalid',
      );
    } on VerificationInProgressException {
      // Already pending with the provider; read the authoritative status.
      await load();
      if (state.status?.kycStatus == KycStatus.pending) {
        state = state.copyWith(phase: VerificationPhase.pendingProvider);
      }
    } catch (_) {
      state = state.copyWith(phase: VerificationPhase.error, submitting: false);
    }
  }

  /// One more correction attempt after a no-match (FEAT-002).
  void correct() {
    if (!state.canCorrect) return;
    state = state.copyWith(
      phase: VerificationPhase.ready,
      correctionUsed: true,
      clearReason: true,
      clearIdentifierError: true,
    );
  }

  VerificationState _stateFor(
    AccountVerification status, {
    SubmissionStatus? submissionStatus,
  }) {
    // A corrected/failed submission is a no-match regardless of the account
    // still reading unverified; the user may correct once.
    final noMatch =
        submissionStatus == SubmissionStatus.corrected ||
        submissionStatus == SubmissionStatus.failed;
    final phase = switch (status.kycStatus) {
      KycStatus.verified => VerificationPhase.verified,
      KycStatus.pending => VerificationPhase.pendingProvider,
      KycStatus.rejected => VerificationPhase.rejected,
      KycStatus.unverified =>
        noMatch ? VerificationPhase.noMatch : VerificationPhase.ready,
    };
    return VerificationState(
      phase: phase,
      status: status,
      correctionUsed: state.correctionUsed,
      reason: phase == VerificationPhase.rejected
          ? 'The identity record did not match.'
          : null,
      online: _online,
    );
  }

  VerificationState _stateForRecord(VerificationRecord record) {
    final status = AccountVerification(
      kycStatus: record.status,
      canCorrect: record.status == KycStatus.unverified,
      method: null,
    );
    final phase = switch (record.status) {
      KycStatus.verified => VerificationPhase.verified,
      KycStatus.pending => VerificationPhase.pendingProvider,
      KycStatus.rejected => VerificationPhase.rejected,
      KycStatus.unverified => VerificationPhase.noMatch,
    };
    return VerificationState(
      phase: phase,
      status: status,
      correctionUsed: state.correctionUsed,
      reason: record.reason,
      online: _online,
    );
  }

  /// Reflects a connectivity change; loading is retried when back online.
  void setOnline(bool online) {
    final wasOffline = !_online;
    _online = online;
    state = state.copyWith(online: online);
    if (online && wasOffline && state.phase == VerificationPhase.error) {
      load();
    }
  }
}

final verificationControllerProvider =
    NotifierProvider<VerificationController, VerificationState>(
      VerificationController.new,
    );
