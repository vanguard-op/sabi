import 'package:flutter/foundation.dart';

import 'service_summary.dart';

/// A resolved request from the assistant (CONTRACTS.md C-009).
///
/// The client renders confirmations from this structure, never from raw text
/// (FEAT-003/011). Amounts are integer minor units (kobo).
@immutable
class IntentResult {
  const IntentResult({
    required this.intentType,
    this.target,
    this.amount,
    this.currency = 'NGN',
    this.reference,
    this.constraints = const {},
    this.confidence = 0,
    this.language = 'en',
    this.clarifyingQuestion,
    this.candidates = const [],
    this.source = 'model',
  });

  final String intentType;
  final String? target;
  final int? amount;
  final String currency;
  final String? reference;
  final Map<String, dynamic> constraints;
  final double confidence;
  final String language;
  final String? clarifyingQuestion;
  final List<ServiceSummary> candidates;

  /// `model` or `fallback`; a fallback resolution must be confirmed before any
  /// money moves.
  final String source;

  bool get needsClarification =>
      confidence < 0.6 && (clarifyingQuestion?.isNotEmpty ?? false);

  factory IntentResult.fromJson(Map<String, dynamic> json) {
    final amount = json['amount'];
    final candidates = (json['candidates'] as List?) ?? const [];
    return IntentResult(
      intentType: (json['intent_type'] ?? json['intentType'] ?? '').toString(),
      target: json['target']?.toString(),
      amount: amount is num ? amount.toInt() : null,
      currency: (json['currency'] ?? 'NGN').toString(),
      reference: json['reference']?.toString(),
      constraints: (json['constraints'] as Map?)?.cast<String, dynamic>() ?? {},
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      language: (json['language'] ?? 'en').toString(),
      clarifyingQuestion:
          (json['clarifying_question'] ?? json['clarifyingQuestion'])
              ?.toString(),
      candidates: candidates
          .whereType<Map>()
          .map((e) => ServiceSummary.fromJson(e.cast<String, dynamic>()))
          .toList(growable: false),
      source: (json['source'] ?? 'model').toString(),
    );
  }
}
