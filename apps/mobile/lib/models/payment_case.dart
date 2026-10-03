import 'package:flutter/foundation.dart';

/// Why a case was opened (schema.md `PaymentCase.type`).
enum CaseType {
  failedNoDelivery,
  disputed,
  refund,
  receiptMissing;

  static CaseType parse(String raw) => switch (raw) {
    'disputed' => CaseType.disputed,
    'refund' => CaseType.refund,
    'receipt_missing' || 'receiptMissing' => CaseType.receiptMissing,
    _ => CaseType.failedNoDelivery,
  };

  String get wire => switch (this) {
    CaseType.failedNoDelivery => 'failed_no_delivery',
    CaseType.disputed => 'disputed',
    CaseType.refund => 'refund',
    CaseType.receiptMissing => 'receipt_missing',
  };
}

/// The case state machine (schema.md `PaymentCase.status`). The user-facing
/// states on screen 8 are derived from these plus the payment status, so the
/// label the user reads always matches the record.
enum CaseStatus {
  open,
  awaitingProvider,
  resolved,
  escalated,
  closed;

  static CaseStatus parse(String raw) => switch (raw) {
    'awaiting_provider' || 'awaitingProvider' => CaseStatus.awaitingProvider,
    'resolved' => CaseStatus.resolved,
    'escalated' => CaseStatus.escalated,
    'closed' => CaseStatus.closed,
    _ => CaseStatus.open,
  };

  String get wire => switch (this) {
    CaseStatus.open => 'open',
    CaseStatus.awaitingProvider => 'awaiting_provider',
    CaseStatus.resolved => 'resolved',
    CaseStatus.escalated => 'escalated',
    CaseStatus.closed => 'closed',
  };

  /// Whether the case is still being worked, so the screen keeps polling and
  /// never claims a resolution that has not happened.
  bool get isActive => this == CaseStatus.open || this == CaseStatus.awaitingProvider;
}

/// The states the Case screen shows (docs/Sabi/screens/08-case.md). Derived
/// from the case and payment records so a user reads one consistent story:
/// a dispute under reconciliation, a refund in flight, the biller's window,
/// an escalation, or a settled outcome.
enum CasePresentation {
  pending,
  reconciling,
  refundInitiated,
  awaitingBiller,
  escalated,
  resolved;

  static CasePresentation resolve({
    required CaseType type,
    required CaseStatus status,
    required String paymentStatus,
  }) => switch (status) {
    CaseStatus.escalated => CasePresentation.escalated,
    CaseStatus.resolved || CaseStatus.closed => CasePresentation.resolved,
    CaseStatus.awaitingProvider => CasePresentation.awaitingBiller,
    CaseStatus.open => switch (paymentStatus) {
      'reversed' || 'refunded' => CasePresentation.refundInitiated,
      'failed' => switch (type) {
        CaseType.failedNoDelivery || CaseType.refund =>
          CasePresentation.reconciling,
        _ => CasePresentation.pending,
      },
      _ => CasePresentation.pending,
    },
  };
}

/// A case tracking a failed, reversed, or disputed payment (FEAT-009; schema.md
/// `PaymentCase`). It drives screen 8 to a resolution and is never altered to
/// hide a failure.
@immutable
class PaymentCase {
  const PaymentCase({
    required this.id,
    required this.paymentId,
    required this.type,
    required this.status,
    required this.assigneeRole,
    required this.openedAt,
    required this.updatedAt,
    this.resolvedAt,
  });

  final String id;
  final String paymentId;
  final CaseType type;
  final CaseStatus status;
  final String assigneeRole;
  final DateTime openedAt;
  final DateTime updatedAt;
  final DateTime? resolvedAt;

  factory PaymentCase.fromJson(Map<String, dynamic> json) => PaymentCase(
    id: json['id'].toString(),
    paymentId: json['paymentId'].toString(),
    type: CaseType.parse((json['type'] ?? 'failed_no_delivery').toString()),
    status: CaseStatus.parse((json['status'] ?? 'open').toString()),
    assigneeRole: (json['assigneeRole'] ?? '').toString(),
    openedAt: _date(json['openedAt']) ?? DateTime(0),
    updatedAt: _date(json['updatedAt']) ?? DateTime(0),
    resolvedAt: _date(json['resolvedAt']),
  );
}

/// One state change on a payment, append-only, newest last as returned by
/// C-027 (schema.md `PaymentEvent`). The case timeline renders these newest
/// first.
@immutable
class PaymentEvent {
  const PaymentEvent({
    required this.id,
    required this.paymentId,
    required this.status,
    required this.actor,
    required this.occurredAt,
    required this.createdAt,
    this.detail,
  });

  final String id;
  final String paymentId;
  final String status;
  final String actor;
  final String? detail;
  final DateTime occurredAt;
  final DateTime createdAt;

  factory PaymentEvent.fromJson(Map<String, dynamic> json) => PaymentEvent(
    id: json['id'].toString(),
    paymentId: json['paymentId'].toString(),
    status: (json['status'] ?? 'pending').toString(),
    actor: (json['actor'] ?? 'system').toString(),
    detail: json['detail']?.toString(),
    occurredAt: _date(json['occurredAt']) ?? DateTime(0),
    createdAt: _date(json['createdAt']) ?? DateTime(0),
  );
}

/// A case with its payment and timeline (C-027).
@immutable
class CaseDetail {
  const CaseDetail({
    required this.paymentCase,
    required this.payment,
    required this.timeline,
  });

  final PaymentCase paymentCase;
  final CasePayment payment;
  final List<PaymentEvent> timeline;

  CasePresentation get presentation => CasePresentation.resolve(
    type: paymentCase.type,
    status: paymentCase.status,
    paymentStatus: payment.status,
  );

  factory CaseDetail.fromJson(Map<String, dynamic> json) => CaseDetail(
    paymentCase: PaymentCase.fromJson(
      (json['case'] as Map).cast<String, dynamic>(),
    ),
    payment: CasePayment.fromJson(
      (json['payment'] as Map).cast<String, dynamic>(),
    ),
    timeline: ((json['timeline'] as List?) ?? const [])
        .map((e) => PaymentEvent.fromJson((e as Map).cast<String, dynamic>()))
        .toList(growable: false),
  );
}

/// The payment under a case (C-027, `PaymentSummary`).
@immutable
class CasePayment {
  const CasePayment({
    required this.paymentId,
    required this.serviceId,
    required this.amount,
    required this.currency,
    required this.payee,
    required this.status,
    required this.channel,
    required this.createdAt,
    required this.updatedAt,
    this.failureReason,
  });

  final String paymentId;
  final String serviceId;

  /// Minor units (kobo).
  final int amount;
  final String currency;
  final String payee;
  final String status;
  final String channel;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? failureReason;

  factory CasePayment.fromJson(Map<String, dynamic> json) => CasePayment(
    paymentId: json['paymentId'].toString(),
    serviceId: json['serviceId'].toString(),
    amount: (json['amount'] as num).toInt(),
    currency: (json['currency'] ?? 'NGN').toString(),
    payee: (json['payee'] ?? '').toString(),
    status: (json['status'] ?? 'pending').toString(),
    channel: (json['channel'] ?? 'app').toString(),
    createdAt: _date(json['createdAt']) ?? DateTime(0),
    updatedAt: _date(json['updatedAt']) ?? DateTime(0),
    failureReason: json['failureReason']?.toString(),
  );
}

DateTime? _date(Object? raw) => DateTime.tryParse(raw?.toString() ?? '');
