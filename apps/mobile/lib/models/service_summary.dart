import 'package:flutter/foundation.dart';

/// A discovery result from the catalogue (CONTRACTS.md C-010 `ServiceSummary`).
///
/// Amounts are integer minor units (kobo) and always paired with `currency`;
/// the wire uses the contract's `service_id`/`collecting_body`/`known_amount`
/// keys. Parsing also tolerates camelCase because the contracts and DELIVERY
/// disagree on case.
@immutable
class ServiceSummary {
  const ServiceSummary({
    required this.serviceId,
    required this.name,
    required this.collectingBody,
    required this.category,
    this.knownAmount,
    this.currency = 'NGN',
    this.status = 'active',
    this.confidence = 0,
  });

  final String serviceId;
  final String name;
  final String collectingBody;
  final String category;

  /// Known amount in minor units (kobo), or null when confirmed at payment.
  final int? knownAmount;
  final String currency;
  final String status;
  final double confidence;

  bool get hasKnownAmount => knownAmount != null;

  /// Serialises to the contract's snake_case shape. Used to hand a discovery
  /// result to the composed-surface renderer.
  Map<String, dynamic> toJson() => {
    'service_id': serviceId,
    'name': name,
    'collecting_body': collectingBody,
    'category': category,
    'known_amount': knownAmount,
    'currency': currency,
    'status': status,
    'confidence': confidence,
  };

  factory ServiceSummary.fromJson(Map<String, dynamic> json) {
    final amount = json['known_amount'] ?? json['knownAmount'];
    return ServiceSummary(
      serviceId: (json['service_id'] ?? json['serviceId'] ?? '').toString(),
      name: (json['name'] ?? '').toString(),
      collectingBody: (json['collecting_body'] ?? json['collectingBody'] ?? '')
          .toString(),
      category: (json['category'] ?? '').toString(),
      knownAmount: amount is num ? amount.toInt() : null,
      currency: (json['currency'] ?? 'NGN').toString(),
      status: (json['status'] ?? 'active').toString(),
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
    );
  }
}
