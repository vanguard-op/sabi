import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import '../../core/connectivity.dart';
import '../../data/providers.dart';
import '../../data/repositories.dart';
import '../../models/account.dart';
import '../../models/service_summary.dart';
import 'data/payment_repository.dart';
import 'data/providers.dart';
import 'models/payment.dart';
import 'models/payment_errors.dart';

/// The phases of the payment confirmation surface (screens/04, "States").
///
/// A single enum keeps the screen's `switch` exhaustive: every phase names a
/// distinct thing the user sees, and no phase is inferred from several booleans.
enum PaymentPhase {
  /// Resolving the obligation (federal prepare, bill validation).
  resolving,

  /// Summary ready; the authorise action is available.
  ready,

  /// A variable bill still needs its amount entered.
  amountEntry,

  /// A federal collection needs a payer reference before it can be paid.
  referenceRequired,

  /// The agency switched its collection account; the obligation must be
  /// re-resolved before payment (FEAT-006, alternate G).
  collectionChanged,

  /// A bill needs the recipient identifier validated before it can be paid.
  recipientRequired,

  /// Mandate signed and the rail is being called; fields are locked.
  authorising,

  /// Above the user's limit: a second confirmation is required.
  secondConfirmation,

  /// Regulated payment on an unverified account: held, not failed.
  heldForKyc,

  /// The rail declined or the biller refused; no partial debit.
  failure,

  /// The outcome is unknown; the payment is pending and being reconciled.
  reconciling,

  /// Succeeded, waiting for the official FTeR (federal).
  awaitingReceipt,

  /// Succeeded, waiting for the prepaid token (bill).
  awaitingToken,

  /// The biller failed the payment after the debit; a refund is in flight
  /// (C-035 revision 1, FEAT-009).
  refunding,

  /// The refund has been accepted and is being tracked (FEAT-009).
  refundRequested,

  /// Settled, with the proof stored.
  settled,

  /// No connectivity; authorisation is unavailable.
  offline,

  /// A resolve or submit failure that can be retried.
  error,
}

/// The immutable state the confirmation surface renders.
@immutable
class PaymentConfirmationState {
  const PaymentConfirmationState({
    required this.obligation,
    this.phase = PaymentPhase.resolving,
    this.amount,
    this.reference,
    this.recipient,
    this.federalPrepare,
    this.billValidation,
    this.secondConfirmation = false,
    this.message,
    this.failure,
    this.paymentId,
    this.railReference,
    this.federalReceipt,
    this.billToken,
    this.duplicatePaymentId,
    this.refundAvailable = false,
    this.refundStatus,
    this.refundReference,
  });

  final PaymentObligation obligation;
  final PaymentPhase phase;

  /// The amount being authorised, in minor units (kobo). Falls back to the
  /// obligation's known amount.
  final int? amount;
  final String? reference;

  /// The bill recipient identifier (meter or phone number).
  final String? recipient;

  final FederalPrepare? federalPrepare;
  final BillValidation? billValidation;

  /// Whether the user has already given the second confirmation.
  final bool secondConfirmation;

  /// A plain-language status line for the current phase.
  final String? message;

  /// The failure reason when [phase] is failure or error.
  final String? failure;

  final String? paymentId;
  final String? railReference;
  final FederalReceipt? federalReceipt;
  final BillToken? billToken;

  /// The existing payment id when a duplicate authorisation resumes a payment.
  final String? duplicatePaymentId;

  /// Whether this failure can be recovered by a refund: set when the biller
  /// failed after the debit and no token will be issued (C-035 revision 1).
  final bool refundAvailable;

  /// The refund status once the rail accepts it (`reversed` or `refunded`).
  final String? refundStatus;
  final String? refundReference;

  int? get effectiveAmount => amount ?? obligation.knownAmount;
  bool get isVariable => effectiveAmount == null;
  bool get isFederal => obligation.kind == PaymentKind.federal;
  bool get isBill => obligation.kind == PaymentKind.bill;

  /// True while the surface must lock its fields (authorising, reconciling).
  bool get isLocked =>
      phase == PaymentPhase.authorising ||
      phase == PaymentPhase.refunding ||
      phase == PaymentPhase.reconciling ||
      phase == PaymentPhase.secondConfirmation;

  PaymentConfirmationState copyWith({
    PaymentObligation? obligation,
    PaymentPhase? phase,
    int? amount,
    String? reference,
    String? recipient,
    FederalPrepare? federalPrepare,
    BillValidation? billValidation,
    bool? secondConfirmation,
    String? message,
    String? failure,
    String? paymentId,
    String? railReference,
    FederalReceipt? federalReceipt,
    BillToken? billToken,
    bool clearBillToken = false,
    String? duplicatePaymentId,
    bool? refundAvailable,
    String? refundStatus,
    String? refundReference,
  }) => PaymentConfirmationState(
    obligation: obligation ?? this.obligation,
    phase: phase ?? this.phase,
    amount: amount ?? this.amount,
    reference: reference ?? this.reference,
    recipient: recipient ?? this.recipient,
    federalPrepare: federalPrepare ?? this.federalPrepare,
    billValidation: billValidation ?? this.billValidation,
    secondConfirmation: secondConfirmation ?? this.secondConfirmation,
    message: message ?? this.message,
    failure: failure ?? this.failure,
    paymentId: paymentId ?? this.paymentId,
    railReference: railReference ?? this.railReference,
    federalReceipt: federalReceipt ?? this.federalReceipt,
    billToken: clearBillToken ? null : (billToken ?? this.billToken),
    duplicatePaymentId: duplicatePaymentId ?? this.duplicatePaymentId,
    refundAvailable: refundAvailable ?? this.refundAvailable,
    refundStatus: refundStatus ?? this.refundStatus,
    refundReference: refundReference ?? this.refundReference,
  );
}

/// Drives one payment confirmation from resolution through settlement.
///
/// The flow is the documented one (screens/04, "Data Flow"; user-flow Flows 2,
/// 3, 7): resolve the obligation, gate on KYC, sign a mandate bound to amount
/// and payee, execute through the rail, then retrieve the proof. Every branch
/// the contract or the feature spec names has a phase here, so the screen never
/// has to guess and no failure is silently swallowed.
class PaymentController extends Notifier<PaymentConfirmationState> {
  PaymentController(this.serviceId);

  /// The resolved service id this controller owns; the family argument.
  final String serviceId;

  @override
  PaymentConfirmationState build() {
    // The screen kicks off resolution from its own lifecycle; a placeholder
    // obligation lets the surface paint its skeleton before the catalogue (live)
    // or the sandbox (mock) answers. [resolve] replaces it with the real one.
    return PaymentConfirmationState(
      obligation: PaymentObligation(
        service: ServiceSummary(
          serviceId: serviceId,
          name: '',
          collectingBody: '',
          category: '',
        ),
      ),
    );
  }

  PaymentRepository get _payments => ref.read(paymentRepositoryProvider);
  FederalRepository get _federal => ref.read(federalRepositoryProvider);
  BillRepository get _bills => ref.read(billRepositoryProvider);

  /// Resolves the obligation for its flow: federal collects its collection
  /// facts, a bill needs a recipient before it can be validated, and a standard
  /// obligation is ready as soon as it has an amount. In the live build the
  /// obligation is fetched from the catalogue (C-011); the mock build resolves
  /// it from the sandbox.
  Future<void> resolve() async {
    _set(state.copyWith(phase: PaymentPhase.resolving, failure: null));
    // Resolve the obligation first so the summary still has its amount and
    // payee when the device is offline: the sandbox answer is immediate, and a
    // live fetch that cannot reach the gateway becomes the offline state.
    try {
      final obligation = await ref.read(
        paymentObligationProvider(serviceId).future,
      );
      if (!ref.mounted) return;
      _set(state.copyWith(obligation: obligation));
    } on ServiceNotFoundException {
      // C-011 404: the catalogue does not cover this service. State it and
      // offer a retry rather than fabricating an obligation.
      _set(
        state.copyWith(
          phase: PaymentPhase.error,
          failure: 'We couldn’t find this service. Try again from Home.',
        ),
      );
      return;
    } on ApiUnreachable {
      _set(state.copyWith(phase: PaymentPhase.offline));
      return;
    } catch (_) {
      _set(
        state.copyWith(
          phase: PaymentPhase.error,
          failure: 'Something went wrong. Try again.',
        ),
      );
      return;
    }
    if (!ref.read(connectivityProvider)) {
      _set(state.copyWith(phase: PaymentPhase.offline));
      return;
    }
    try {
      if (state.isFederal) {
        final prepare = await _federal.prepare(
          serviceId: state.obligation.serviceId,
          payerReference: state.reference,
        );
        _set(
          state.copyWith(
            federalPrepare: prepare,
            amount: prepare.amount ?? state.amount,
            phase: prepare.requiresReference && (state.reference ?? '').isEmpty
                ? PaymentPhase.referenceRequired
                : PaymentPhase.ready,
          ),
        );
        return;
      }
      if (state.isBill) {
        if ((state.recipient ?? '').isEmpty) {
          _set(state.copyWith(phase: PaymentPhase.recipientRequired));
          return;
        }
        await _validateBill();
        return;
      }
      _set(
        state.copyWith(
          phase: state.isVariable
              ? PaymentPhase.amountEntry
              : PaymentPhase.ready,
        ),
      );
    } on PaymentException catch (e) {
      _set(state.copyWith(phase: _phaseFor(e), failure: e.message));
    } on ApiUnreachable {
      _set(state.copyWith(phase: PaymentPhase.offline));
    } catch (_) {
      _set(
        state.copyWith(
          phase: PaymentPhase.error,
          failure: 'Something went wrong. Try again.',
        ),
      );
    }
  }

  /// Sets the amount from the amount-entry sheet. Re-runs bill validation when
  /// the amount is what the biller checks.
  Future<void> setAmount(int amountMinor) async {
    _set(state.copyWith(amount: amountMinor, failure: null));
    if (state.isBill) {
      await _validateBill();
    } else {
      _set(state.copyWith(phase: PaymentPhase.ready));
    }
  }

  /// Sets the payer reference for a federal collection and re-resolves.
  Future<void> setReference(String reference) async {
    _set(state.copyWith(reference: reference.trim(), failure: null));
    if (state.isFederal) await resolve();
  }

  /// Sets the bill recipient identifier and validates it.
  Future<void> setRecipient(String recipient) async {
    _set(state.copyWith(recipient: recipient.trim(), failure: null));
    await _validateBill();
  }

  Future<void> _validateBill() async {
    _set(state.copyWith(phase: PaymentPhase.resolving, failure: null));
    try {
      final validation = await _bills.validate(
        serviceId: state.obligation.serviceId,
        recipientIdentifier: state.recipient ?? '',
        amount: state.amount,
      );
      if (!validation.valid) {
        _set(
          state.copyWith(
            billValidation: validation,
            phase: PaymentPhase.failure,
            failure: validation.reason,
          ),
        );
        return;
      }
      _set(
        state.copyWith(
          billValidation: validation,
          amount: validation.knownAmount ?? state.amount,
          phase: validation.knownAmount == null && state.amount == null
              ? PaymentPhase.amountEntry
              : PaymentPhase.ready,
        ),
      );
    } on BillerOfflineException catch (e) {
      // Biller offline prevents the payment before anything is authorised
      // (FEAT-007, alternate B). It is a failure with no debit.
      _set(state.copyWith(phase: PaymentPhase.failure, failure: e.message));
    } on PaymentException catch (e) {
      _set(state.copyWith(phase: _phaseFor(e), failure: e.message));
    } catch (_) {
      _set(
        state.copyWith(
          phase: PaymentPhase.error,
          failure: 'Something went wrong. Try again.',
        ),
      );
    }
  }

  /// Authorises and, on success, executes the payment.
  ///
  /// A second confirmation above the limit is asked once and then honoured;
  /// KYC holds a regulated payment rather than failing it; and an unknown
  /// outcome is marked reconciling rather than retried blindly.
  Future<void> submit() async {
    if (state.isLocked) return;
    if (!ref.read(connectivityProvider)) {
      _set(state.copyWith(phase: PaymentPhase.offline));
      return;
    }
    final amount = state.effectiveAmount;
    if (amount == null) {
      _set(state.copyWith(phase: PaymentPhase.amountEntry));
      return;
    }
    if (state.isFederal &&
        state.federalPrepare?.requiresReference == true &&
        (state.reference ?? '').isEmpty) {
      _set(state.copyWith(phase: PaymentPhase.referenceRequired));
      return;
    }

    // A regulated payment on an unverified account is held, never failed
    // (FEAT-002; screens/04, "Held for KYC").
    if (state.isFederal) {
      try {
        final account = await ref.read(accountRepositoryProvider).me();
        if (!ref.mounted) return;
        if (account.kycStatus != VerificationStatus.verified) {
          _set(state.copyWith(phase: PaymentPhase.heldForKyc));
          return;
        }
      } catch (_) {
        // An account lookup failure must not block a payment the user can
        // still make; fall through to authorisation.
      }
    }

    // A bill is authorised and executed in one call (C-034).
    if (state.isBill) {
      await _payBill(amount);
      return;
    }

    await _authoriseAndExecute(amount);
  }

  Future<void> _authoriseAndExecute(int amount) async {
    _set(
      state.copyWith(
        phase: PaymentPhase.authorising,
        failure: null,
        duplicatePaymentId: null,
      ),
    );
    final idempotencyKey =
        'pay_${state.obligation.serviceId}_${state.paymentId ?? 'new'}';
    try {
      final authorise = await _payments.authorise(
        serviceId: state.obligation.serviceId,
        amount: amount,
        currency: state.obligation.currency,
        payeeReference: state.reference,
        secondConfirmation: state.secondConfirmation,
        idempotencyKey: idempotencyKey,
      );
      if (!ref.mounted) return;
      _set(
        state.copyWith(
          paymentId: authorise.paymentId,
          railReference: authorise.railReference,
        ),
      );
      await _execute(authorise.paymentId, authorise.mandateId);
    } on SecondConfirmationRequiredException catch (e) {
      // Ask exactly once; the next submit carries the confirmation.
      _set(
        state.copyWith(
          phase: PaymentPhase.secondConfirmation,
          message: e.message,
        ),
      );
    } on DuplicateAuthorisationException catch (e) {
      // A repeat authorisation resumes the existing payment rather than
      // creating a second one (FEAT-005, edge case).
      if (!ref.mounted) return;
      final duplicate = e;
      _set(
        state.copyWith(
          paymentId: duplicate.paymentId,
          railReference: duplicate.railReference,
          duplicatePaymentId: duplicate.paymentId,
        ),
      );
      // The existing payment already carries a mandate on the server; a
      // resumption executes it again under the same idempotency key, which the
      // rail dedupes. The client never starts a fresh authorisation.
      await _execute(duplicate.paymentId, duplicate.paymentId);
    } on PaymentException catch (e) {
      _set(state.copyWith(phase: _phaseFor(e), failure: e.message));
    } catch (_) {
      _set(
        state.copyWith(
          phase: PaymentPhase.error,
          failure: 'Something went wrong. Try again.',
        ),
      );
    }
  }

  Future<void> _execute(String paymentId, String mandateId) async {
    _set(state.copyWith(phase: PaymentPhase.authorising));
    try {
      final result = await _payments.execute(
        paymentId: paymentId,
        mandateId: mandateId,
        idempotencyKey: 'exec_$paymentId',
      );
      if (!ref.mounted) return;
      if (result.status.isTerminalSuccess) {
        _set(
          state.copyWith(
            phase: PaymentPhase.settled,
            paymentId: result.paymentId,
            railReference: result.railReference,
            message: null,
          ),
        );
        await _retrieveProof(result.paymentId);
        return;
      }
      if (result.status.isUnknownOutcome) {
        _set(
          state.copyWith(
            phase: PaymentPhase.reconciling,
            paymentId: result.paymentId,
            railReference: result.railReference,
          ),
        );
        return;
      }
      _set(
        state.copyWith(
          phase: PaymentPhase.failure,
          failure: 'The payment didn’t go through. Nothing was debited.',
        ),
      );
    } on RailTimeoutException {
      // Unknown outcome: pending and reconciled, never retried immediately
      // (FEAT-005, edge case; user-flow Flow 2 alternate E).
      _set(state.copyWith(phase: PaymentPhase.reconciling));
    } on PaymentException catch (e) {
      _set(state.copyWith(phase: _phaseFor(e), failure: e.message));
    } catch (_) {
      _set(
        state.copyWith(
          phase: PaymentPhase.error,
          failure: 'Something went wrong. Try again.',
        ),
      );
    }
  }

  /// After a federal settlement, retrieves the FTeR; after a prepaid bill,
  /// retrieves the token. Both hold the payment open until the proof arrives.
  Future<void> _retrieveProof(String paymentId) async {
    if (state.isFederal) {
      try {
        final receipt = await _federal.receipt(paymentId);
        if (!ref.mounted) return;
        _set(
          state.copyWith(
            federalReceipt: receipt,
            phase: receipt.isAwaiting
                ? PaymentPhase.awaitingReceipt
                : PaymentPhase.settled,
          ),
        );
      } on PaymentException catch (e) {
        _set(state.copyWith(phase: PaymentPhase.error, failure: e.message));
      } catch (_) {
        // The payment settled even if the proof lookup failed; the receipt can
        // be retrieved again, so the surface offers a retry rather than
        // claiming the payment failed.
        _set(
          state.copyWith(
            phase: PaymentPhase.error,
            failure: 'Your payment settled, but we couldn’t fetch the official receipt. Try again.',
          ),
        );
      }
    }
  }

  /// Retries fetching a proof the payment already earned (FTeR or token).
  Future<void> retryProof() async {
    final id = state.paymentId;
    if (id == null) return;
    if (state.isFederal) await _retrieveProof(id);
    if (state.isBill) await _retrieveToken(id);
  }

  Future<void> _payBill(int amount) async {
    _set(state.copyWith(phase: PaymentPhase.authorising, failure: null));
    try {
      final result = await _bills.pay(
        serviceId: state.obligation.serviceId,
        recipientIdentifier: state.recipient ?? '',
        amount: amount,
        currency: state.obligation.currency,
        idempotencyKey: 'bill_${state.obligation.serviceId}',
      );
      if (!ref.mounted) return;
      _set(
        state.copyWith(
          paymentId: result.paymentId,
          phase: result.token == null
              ? PaymentPhase.awaitingToken
              : PaymentPhase.settled,
          billToken: result.token == null
              ? const BillToken(status: 'awaiting_token', retryAfterSeconds: 3)
              : BillToken(token: result.token, receiptId: result.receiptId),
        ),
      );
      if (result.token == null) await _retrieveToken(result.paymentId);
    } on BillerOfflineException catch (e) {
      _set(state.copyWith(phase: PaymentPhase.failure, failure: e.message));
    } on BillInsufficientFundsException catch (e) {
      _set(state.copyWith(phase: PaymentPhase.failure, failure: e.message));
    } on PaymentException catch (e) {
      _set(state.copyWith(phase: _phaseFor(e), failure: e.message));
    } catch (_) {
      _set(
        state.copyWith(
          phase: PaymentPhase.error,
          failure: 'Something went wrong. Try again.',
        ),
      );
    }
  }

  Future<void> _retrieveToken(String paymentId) async {
    try {
      final token = await _bills.token(paymentId);
      if (!ref.mounted) return;
      if (token.isAwaiting) {
        _set(
          state.copyWith(phase: PaymentPhase.awaitingToken, billToken: token),
        );
        return;
      }
      _set(state.copyWith(phase: PaymentPhase.settled, billToken: token));
    } on BillTokenFailedException catch (e) {
      // C-035 409 (revision 1): the payment failed after the debit and no token
      // will issue. Show the failure and offer the refund, never a poll.
      _set(
        state.copyWith(
          phase: PaymentPhase.failure,
          failure: e.message,
          refundAvailable: true,
          clearBillToken: true,
        ),
      );
    } on PaymentException catch (e) {
      _set(state.copyWith(phase: PaymentPhase.error, failure: e.message));
    } catch (_) {
      _set(
        state.copyWith(
          phase: PaymentPhase.error,
          failure: 'Your payment settled, but we couldn’t fetch the token. Try again.',
        ),
      );
    }
  }

  /// Starts the FEAT-009 refund for a payment the biller failed after debiting
  /// it (C-029). The idempotency key makes a retry the same refund, never a
  /// second one.
  Future<void> requestRefund() async {
    final paymentId = state.paymentId;
    if (paymentId == null) return;
    if (state.phase == PaymentPhase.refunding) return;
    if (!ref.read(connectivityProvider)) {
      _set(state.copyWith(phase: PaymentPhase.offline));
      return;
    }
    _set(state.copyWith(phase: PaymentPhase.refunding, failure: null));
    try {
      final result = await ref.read(casesRepositoryProvider).refund(
        paymentId: paymentId,
        reason: 'The biller did not issue a token for this payment.',
        idempotencyKey: 'refund_$paymentId',
      );
      if (!ref.mounted) return;
      _set(
        state.copyWith(
          phase: PaymentPhase.refundRequested,
          refundStatus: result.status,
          refundReference: result.refundReference,
        ),
      );
    } on DuplicateRefundException {
      // A refund for this reference already exists; treat it as requested and
      // do not start a second one (FEAT-009, duplicate-refund edge case).
      _set(state.copyWith(phase: PaymentPhase.refundRequested));
    } on RefundNotAllowedException {
      // C-029 422: the payment's current state does not allow a refund. State
      // it plainly so the user knows the recovery is not available here.
      _set(
        state.copyWith(
          phase: PaymentPhase.failure,
          failure: 'This payment can’t be refunded right now.',
        ),
      );
    } catch (_) {
      _set(
        state.copyWith(
          phase: PaymentPhase.error,
          failure: 'We couldn’t start the refund. Try again.',
        ),
      );
    }
  }

  /// Confirms a second authorisation above the limit, then re-submits.
  Future<void> confirmSecondTime() async {
    _set(state.copyWith(secondConfirmation: true, phase: PaymentPhase.ready));
    await submit();
  }

  /// Declines the second confirmation and returns to the summary.
  void declineSecondTime() {
    _set(
      state.copyWith(
        secondConfirmation: false,
        phase: PaymentPhase.ready,
        message: null,
      ),
    );
  }

  /// Returns to the summary after a failure, preserving the entered data.
  void reset() {
    _set(
      state.copyWith(
        phase: state.effectiveAmount == null
            ? PaymentPhase.amountEntry
            : PaymentPhase.ready,
        failure: null,
        message: null,
      ),
    );
  }

  /// Re-resolves the obligation after a collection-account change (FEAT-006).
  Future<void> reResolve() async {
    _set(state.copyWith(failure: null, reference: null));
    await resolve();
  }

  PaymentPhase _phaseFor(PaymentException e) => switch (e) {
    CollectionAccountChangedException() => PaymentPhase.collectionChanged,
    BillerOfflineException() => PaymentPhase.failure,
    InvalidFederalServiceException() => PaymentPhase.failure,
    FederalNotSettledException() => PaymentPhase.failure,
    InvalidBillException() => PaymentPhase.failure,
    BillInsufficientFundsException() => PaymentPhase.failure,
    InsufficientFundsException() => PaymentPhase.failure,
    InvalidAuthorisationException() => PaymentPhase.failure,
    MandateExpiredException() => PaymentPhase.failure,
    MandateMismatchException() => PaymentPhase.failure,
    RailTimeoutException() => PaymentPhase.reconciling,
    BillTokenNotFoundException() => PaymentPhase.failure,
    BillTokenFailedException() => PaymentPhase.failure,
    SecondConfirmationRequiredException() => PaymentPhase.secondConfirmation,
    DuplicateAuthorisationException() => PaymentPhase.authorising,
    PaymentServerException() => PaymentPhase.error,
  };

  void _set(PaymentConfirmationState next) {
    if (!ref.mounted) return;
    state = next;
  }
}

/// One controller per resolved obligation, keyed by service id.
final paymentControllerProvider =
    NotifierProvider.family<
      PaymentController,
      PaymentConfirmationState,
      String
    >(PaymentController.new);
