import 'package:flutter/foundation.dart';

/// A discovery result from the catalogue (CONTRACTS.md C-010 `ServiceSummary`).
///
/// Amounts are integer minor units (kobo) and always paired with `currency`;
/// the HTTP wire is camelCase (DELIVERY.md, D-018) and `toJson` emits exactly
/// the catalog's `ServiceResultRow` shape, since the composed discovery
/// surface receives these rows as its context. Parsing tolerates the former
/// snake_case so stored or in-flight payloads keep resolving.
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

  /// Serialises to the camelCase wire shape (C-010, D-018). Used to hand a
  /// discovery result to the composed-surface renderer, which validates it
  /// against the published catalog's camelCase `ServiceResultRow`.
  Map<String, dynamic> toJson() => {
    'serviceId': serviceId,
    'name': name,
    'collectingBody': collectingBody,
    'category': category,
    'knownAmount': knownAmount,
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
