import 'package:flutter/foundation.dart';

/// The kind of proof a receipt carries (schema.md `Receipt.kind`).
enum ReceiptKind {
  officialEReceipt,
  billerConfirmation,
  token;

  static ReceiptKind parse(String raw) => switch (raw) {
    'official_e_receipt' || 'officialEReceipt' => ReceiptKind.officialEReceipt,
    'token' => ReceiptKind.token,
    _ => ReceiptKind.billerConfirmation,
  };

  /// The wire value, so a screen never invents one.
  String get wire => switch (this) {
    ReceiptKind.officialEReceipt => 'official_e_receipt',
    ReceiptKind.billerConfirmation => 'biller_confirmation',
    ReceiptKind.token => 'token',
  };
}

/// Whether the receipt was confirmed against its source (schema.md
/// `Receipt.verificationStatus`). `pending` means the source has not answered
/// yet; it is never rendered as a false negative.
enum ReceiptVerification {
  verified,
  unverified,
  pending;

  static ReceiptVerification parse(String raw) => switch (raw) {
    'verified' => ReceiptVerification.verified,
    'unverified' => ReceiptVerification.unverified,
    _ => ReceiptVerification.pending,
  };
}

/// The three states a receipt shows in the Receipts list: a settled payment
/// whose official identifier is still being checked (awaiting), one confirmed
/// against its source (verified), or one the source could not confirm
/// (unverified). Derived from [ReceiptVerification]; kept separate so the list
/// and the pill share one vocabulary.
enum ReceiptListStatus {
  awaiting,
  verified,
  unverified;

  static ReceiptListStatus fromVerification(ReceiptVerification status) =>
      switch (status) {
        ReceiptVerification.verified => ReceiptListStatus.verified,
        ReceiptVerification.unverified => ReceiptListStatus.unverified,
        ReceiptVerification.pending => ReceiptListStatus.awaiting,
      };
}

/// A stored proof of a completed payment (FEAT-008; schema.md `Receipt`). The
/// payment fields are read across the isolated store boundary, so a receipt is
/// never fabricated (C-024).
@immutable
class Receipt {
  const Receipt({
    required this.id,
    required this.paymentId,
    required this.kind,
    required this.verificationStatus,
    required this.documentRef,
    required this.createdAt,
    this.receiptNumber,
    this.unverifiedReason,
    this.issuedAt,
  });

  final String id;
  final String paymentId;
  final ReceiptKind kind;

  /// The official identifier, such as the FTeR number; null until it exists.
  final String? receiptNumber;

  final ReceiptVerification verificationStatus;

  /// Plain reason the receipt is unverified (FEAT-008); null when verified or
  /// pending.
  final String? unverifiedReason;

  final String documentRef;
  final DateTime? issuedAt;
  final DateTime createdAt;

  /// The list status derived from the verification state.
  ReceiptListStatus get listStatus =>
      ReceiptListStatus.fromVerification(verificationStatus);

  factory Receipt.fromJson(Map<String, dynamic> json) => Receipt(
    id: json['id'].toString(),
    paymentId: json['paymentId'].toString(),
    kind: ReceiptKind.parse((json['kind'] ?? 'biller_confirmation').toString()),
    receiptNumber: json['receiptNumber']?.toString(),
    verificationStatus: ReceiptVerification.parse(
      (json['verificationStatus'] ?? 'pending').toString(),
    ),
    unverifiedReason: json['unverifiedReason']?.toString(),
    documentRef: (json['documentRef'] ?? '').toString(),
    issuedAt: _date(json['issuedAt']),
    createdAt: _date(json['createdAt']) ?? DateTime(0),
  );
}

/// The payment a receipt proves (C-024, `PaymentSummary`).
@immutable
class ReceiptPayment {
  const ReceiptPayment({
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

  factory ReceiptPayment.fromJson(Map<String, dynamic> json) => ReceiptPayment(
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

/// A receipt with the payment it proves (C-024).
@immutable
class ReceiptDetail {
  const ReceiptDetail({required this.receipt, required this.payment});

  final Receipt receipt;
  final ReceiptPayment payment;

  factory ReceiptDetail.fromJson(Map<String, dynamic> json) => ReceiptDetail(
    receipt: Receipt.fromJson((json['receipt'] as Map).cast<String, dynamic>()),
    payment: ReceiptPayment.fromJson(
      (json['payment'] as Map).cast<String, dynamic>(),
    ),
  );
}

/// The stored document behind a receipt (C-025), fetched only when the user
/// exports or shares.
@immutable
class ReceiptDocument {
  const ReceiptDocument({
    required this.documentRef,
    required this.contentType,
    this.shareToken,
  });

  final String documentRef;
  final String contentType;
  final String? shareToken;

  factory ReceiptDocument.fromJson(Map<String, dynamic> json) => ReceiptDocument(
    documentRef: json['documentRef'].toString(),
    contentType: json['contentType'].toString(),
    shareToken: json['shareToken']?.toString(),
  );
}

DateTime? _date(Object? raw) =>
    DateTime.tryParse(raw?.toString() ?? '');
