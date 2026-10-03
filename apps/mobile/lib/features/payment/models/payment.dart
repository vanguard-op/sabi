import 'package:flutter/foundation.dart';

import '../../../models/service_summary.dart';

/// The states a payment moves through (CONTRACTS.md C-017 `status`, C-018).
///
/// The client folds the wire vocabulary into the states the confirmation
/// surface renders; unknown values resolve to [pending] rather than inventing a
/// state, so a new value from the rail never crashes a screen.
enum PaymentState {
  initiated,
  authorized,
  pending,
  succeeded,
  failed,
  reversed,
  refunded;

  static PaymentState parse(String? raw) => switch (raw) {
    'initiated' => PaymentState.initiated,
    'authorized' || 'authorised' => PaymentState.authorized,
    'pending' => PaymentState.pending,
    'succeeded' => PaymentState.succeeded,
    'failed' => PaymentState.failed,
    'reversed' => PaymentState.reversed,
    'refunded' => PaymentState.refunded,
    _ => PaymentState.pending,
  };

  bool get isTerminalSuccess => this == PaymentState.succeeded;
  bool get isUnknownOutcome =>
      this == PaymentState.pending || this == PaymentState.initiated;
}

/// The result of signing a mandate for a specific amount and payee
/// (CONTRACTS.md C-017). The payment is not executed until the mandate is
/// consumed through C-018.
@immutable
class AuthoriseResult {
  const AuthoriseResult({
    required this.paymentId,
    required this.status,
    required this.mandateId,
    this.railReference,
  });

  final String paymentId;
  final PaymentState status;
  final String mandateId;
  final String? railReference;

  factory AuthoriseResult.fromJson(Map<String, dynamic> json) =>
      AuthoriseResult(
        paymentId: json['paymentId'].toString(),
        status: PaymentState.parse(json['status']?.toString()),
        mandateId: json['mandateId'].toString(),
        railReference: json['railReference']?.toString(),
      );
}

/// The result of executing a signed mandate (CONTRACTS.md C-018).
@immutable
class ExecuteResult {
  const ExecuteResult({
    required this.paymentId,
    required this.status,
    this.railReference,
  });

  final String paymentId;
  final PaymentState status;
  final String? railReference;

  factory ExecuteResult.fromJson(Map<String, dynamic> json) => ExecuteResult(
    paymentId: json['paymentId'].toString(),
    status: PaymentState.parse(json['status']?.toString()),
    railReference: json['railReference']?.toString(),
  );
}

/// One payment in the account's payment list (CONTRACTS.md C-019
/// `PaymentSummary`). Amounts are integer minor units (kobo).
@immutable
class PaymentSummary {
  const PaymentSummary({
    required this.paymentId,
    required this.serviceId,
    required this.amount,
    required this.currency,
    required this.payee,
    required this.status,
    required this.channel,
    required this.createdAt,
    required this.updatedAt,
  });

  final String paymentId;
  final String serviceId;
  final int amount;
  final String currency;
  final String payee;
  final PaymentState status;
  final String channel;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory PaymentSummary.fromJson(Map<String, dynamic> json) => PaymentSummary(
    paymentId: json['paymentId'].toString(),
    serviceId: json['serviceId'].toString(),
    amount: (json['amount'] as num).toInt(),
    currency: (json['currency'] ?? 'NGN').toString(),
    payee: json['payee'].toString(),
    status: PaymentState.parse(json['status']?.toString()),
    channel: (json['channel'] ?? 'app').toString(),
    createdAt: _parseTime(json['createdAt']),
    updatedAt: _parseTime(json['updatedAt']),
  );
}

DateTime _parseTime(Object? raw) =>
    DateTime.tryParse(raw?.toString() ?? '')?.toUtc() ?? DateTime.utc(0);

/// A federal obligation resolved before payment (CONTRACTS.md C-030).
///
/// `requiresReference` marks a collection that is not paid without a payer
/// reference; `instructions` explains how to obtain one (FEAT-006).
@immutable
class FederalPrepare {
  const FederalPrepare({
    required this.serviceId,
    required this.collectingBody,
    this.amount,
    this.currency = 'NGN',
    required this.requiresReference,
    this.instructions,
  });

  final String serviceId;
  final String collectingBody;

  /// Minor units (kobo), or null when the amount is confirmed at payment.
  final int? amount;
  final String currency;
  final bool requiresReference;
  final String? instructions;

  bool get hasKnownAmount => amount != null;

  factory FederalPrepare.fromJson(Map<String, dynamic> json) => FederalPrepare(
    serviceId: json['serviceId'].toString(),
    collectingBody: json['collectingBody'].toString(),
    amount: (json['amount'] as num?)?.toInt(),
    currency: (json['currency'] ?? 'NGN').toString(),
    requiresReference: json['requiresReference'] == true,
    instructions: json['instructions']?.toString(),
  );
}

/// The official FTeR state for a succeeded federal payment (CONTRACTS.md
/// C-031). `receiptId` is null while the central platform has not issued it,
/// in which case [status] is `awaiting_receipt`.
@immutable
class FederalReceipt {
  const FederalReceipt({
    this.receiptId,
    this.receiptNumber,
    this.verificationStatus,
    this.status,
    this.retryAfterSeconds,
  });

  final String? receiptId;
  final String? receiptNumber;

  /// `verified`, `unverified`, or `pending`.
  final String? verificationStatus;

  /// `awaiting_receipt` while the official receipt has not arrived.
  final String? status;
  final int? retryAfterSeconds;

  bool get isAwaiting => receiptId == null;

  factory FederalReceipt.fromJson(Map<String, dynamic> json) => FederalReceipt(
    receiptId: json['receiptId']?.toString(),
    receiptNumber: json['receiptNumber']?.toString(),
    verificationStatus: json['verificationStatus']?.toString(),
    status: json['status']?.toString(),
    retryAfterSeconds: (json['retryAfterSeconds'] as num?)?.toInt(),
  );
}

/// The accepted amount band for a variable bill, in minor units (CONTRACTS.md
/// C-033 `range`).
@immutable
class BillRange {
  const BillRange({required this.minimum, required this.maximum});

  final int minimum;
  final int maximum;

  factory BillRange.fromJson(Map<String, dynamic> json) => BillRange(
    minimum: (json['minimum'] as num).toInt(),
    maximum: (json['maximum'] as num).toInt(),
  );
}

/// The result of validating a bill recipient and amount (CONTRACTS.md C-033).
@immutable
class BillValidation {
  const BillValidation({
    required this.valid,
    required this.recipientIdentifier,
    this.knownAmount,
    this.currency = 'NGN',
    this.range,
    this.reason,
  });

  final bool valid;
  final String recipientIdentifier;
  final int? knownAmount;
  final String currency;
  final BillRange? range;
  final String? reason;

  factory BillValidation.fromJson(Map<String, dynamic> json) => BillValidation(
    valid: json['valid'] == true,
    recipientIdentifier: json['recipientIdentifier']?.toString() ?? '',
    knownAmount: (json['knownAmount'] as num?)?.toInt(),
    currency: (json['currency'] ?? 'NGN').toString(),
    range: json['range'] is Map
        ? BillRange.fromJson((json['range'] as Map).cast<String, dynamic>())
        : null,
    reason: json['reason']?.toString(),
  );
}

/// The result of paying a bill in one step (CONTRACTS.md C-034). A prepaid
/// bill returns [token]; all bills return a receipt id once stored.
@immutable
class BillPaymentResult {
  const BillPaymentResult({
    required this.paymentId,
    required this.status,
    this.token,
    this.receiptId,
  });

  final String paymentId;
  final PaymentState status;
  final String? token;
  final String? receiptId;

  factory BillPaymentResult.fromJson(Map<String, dynamic> json) =>
      BillPaymentResult(
        paymentId: json['paymentId'].toString(),
        status: PaymentState.parse(json['status']?.toString()),
        token: json['token']?.toString(),
        receiptId: json['receiptId']?.toString(),
      );
}

/// A prepaid token that has not returned yet (CONTRACTS.md C-035). The payment
/// is held open and retried rather than marked complete without the token.
@immutable
class BillToken {
  const BillToken({
    this.token,
    this.receiptId,
    this.status,
    this.retryAfterSeconds,
  });

  final String? token;
  final String? receiptId;
  final String? status;
  final int? retryAfterSeconds;

  bool get isAwaiting => token == null;

  factory BillToken.fromJson(Map<String, dynamic> json) => BillToken(
    token: json['token']?.toString(),
    receiptId: json['receiptId']?.toString(),
    status: json['status']?.toString(),
    retryAfterSeconds: (json['retryAfterSeconds'] as num?)?.toInt(),
  );
}

/// The context a payment confirmation is opened with: the resolved obligation
/// the user is about to authorise. Only a [ServiceSummary] is available from
/// discovery today, so this carries the fields the summary can supply.
@immutable
class PaymentObligation {
  const PaymentObligation({
    required this.service,
    this.amount,
    this.reference,
    this.charges,
    this.currency = 'NGN',
    this.kind = PaymentKind.standard,
  });

  final ServiceSummary service;

  /// Minor units (kobo), or null when variable and not yet entered.
  final int? amount;
  final String? reference;
  final int? charges;
  final String currency;
  final PaymentKind kind;

  String get serviceId => service.serviceId;
  String get payee => service.collectingBody;
  int? get knownAmount => amount ?? service.knownAmount;
  bool get isVariable => knownAmount == null;

  PaymentObligation copyWith({int? amount, String? reference}) =>
      PaymentObligation(
        service: service,
        amount: amount ?? this.amount,
        reference: reference ?? this.reference,
        charges: charges,
        currency: currency,
        kind: kind,
      );

  factory PaymentObligation.fromService(
    ServiceSummary service, {
    PaymentKind kind = PaymentKind.standard,
    int? charges,
    String? reference,
  }) => PaymentObligation(
    service: service,
    charges: charges,
    reference: reference,
    kind: kind,
  );
}

/// The collection family a payment belongs to, which selects the surface's
/// flow. Federal and bill flows carry extra resolve/validate steps before the
/// shared authorisation (FEAT-006, FEAT-007).
enum PaymentKind { standard, federal, bill }

/// The kind of identifier a biller expects, which decides the recipient field's
/// label and hint (FEAT-007).
///
/// An electricity bill wants a meter number, airtime wants a phone number, and
/// a water or television account wants an account number; the category and name
/// the catalogue returns are the only signal the client has, so an unrecognised
/// biller falls back to [generic] rather than guessing.
enum BillRecipientKind {
  meter,
  phone,
  account,
  generic;

  /// Classifies a service from its catalogue name and category.
  ///
  /// The catalogue returns a free-text `name` and a coarse `category` (for
  /// example "Biller" or "Government"), so the match stays tolerant: a known
  /// household service is recognised from either field, and anything else is
  /// [generic].
  static BillRecipientKind forService({
    required String name,
    required String category,
  }) {
    final haystack = '${name.toLowerCase()} ${category.toLowerCase()}';
    bool has(String token) => haystack.contains(token);

    // Electricity first: "meter" and "token" also appear in airtime copy, so
    // the power words are checked before the telecom ones.
    if (has('electric') ||
        has('meter') ||
        has('prepaid') ||
        has('power') ||
        has('energy')) {
      return BillRecipientKind.meter;
    }
    if (has('airtime') ||
        has('data') ||
        has('mobile') ||
        has('phone') ||
        has('telecom') ||
        has('mtn') ||
        has('airtel') ||
        has('glo') ||
        has('9mobile')) {
      return BillRecipientKind.phone;
    }
    if (has('water') ||
        has('television') ||
        has('cable') ||
        has('dstv') ||
        has('gotv') ||
        has('startimes') ||
        has('broadband') ||
        has('subscription') ||
        has('account')) {
      return BillRecipientKind.account;
    }
    return BillRecipientKind.generic;
  }
}
