import 'package:flutter/foundation.dart';

/// A saved payment method shown on Account. Payment rails land in a later phase;
/// this is the display shape the account surface needs today.
@immutable
class PaymentMethod {
  const PaymentMethod({
    required this.id,
    required this.label,
    required this.kind,
    this.isDefault = false,
  });

  final String id;
  final String label;

  /// e.g. `wallet`, `card`, `bank`.
  final String kind;
  final bool isDefault;
}
