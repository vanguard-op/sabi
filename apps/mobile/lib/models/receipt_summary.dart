import 'package:flutter/foundation.dart';

/// The status shown by a Status Pill (screens.md). Colour is never the only
/// signal: every value carries a glyph and a label.
enum PaymentStatus {
  pending,
  settled,
  failed,
  awaitingReceipt;

  static PaymentStatus parse(String raw) => switch (raw) {
    'settled' => PaymentStatus.settled,
    'failed' => PaymentStatus.failed,
    'awaiting_receipt' || 'awaitingReceipt' => PaymentStatus.awaitingReceipt,
    _ => PaymentStatus.pending,
  };
}

/// A recent receipt as shown on Home and Receipts. Receipts are contracted in a
/// later phase; this is the shape the display needs today.
@immutable
class ReceiptSummary {
  const ReceiptSummary({
    required this.id,
    required this.reference,
    required this.payee,
    required this.amount,
    required this.currency,
    required this.issuedAt,
    required this.kind,
    required this.status,
  });

  final String id;
  final String reference;
  final String payee;

  /// Minor units (kobo).
  final int amount;
  final String currency;
  final DateTime issuedAt;

  /// The receipt kind, e.g. `government` or `biller`.
  final String kind;
  final PaymentStatus status;

  factory ReceiptSummary.fromJson(Map<String, dynamic> json) => ReceiptSummary(
    id: json['id'].toString(),
    reference: json['reference'].toString(),
    payee: json['payee'].toString(),
    amount: (json['amount'] as num).toInt(),
    currency: (json['currency'] ?? 'NGN').toString(),
    issuedAt:
        DateTime.tryParse(json['issuedAt']?.toString() ?? '') ?? DateTime(0),
    kind: (json['kind'] ?? 'biller').toString(),
    status: PaymentStatus.parse((json['status'] ?? 'pending').toString()),
  );
}
