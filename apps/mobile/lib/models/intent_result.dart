import 'package:flutter/foundation.dart';

import 'service_summary.dart';

/// The serving confidence cutoff below which the model asks a clarifying
/// question rather than resolving a payment intent, and below which catalogue
/// ranking reports no match (MQ-001/MQ-002, D-017/D-019).
const double intentServingConfidenceCutoff = 0.70;

/// The `non_command` intent type: a greeting, thanks, or small talk. Answered
/// conversationally and never recorded as a coverage miss (FEAT-003, C-009).
const String intentTypeNonCommand = 'non_command';

/// The most prior turns the client may include in one resolution request. C-009
/// bounds `history` at six entries; the client trims older entries first.
const int intentHistoryMaxEntries = 6;

/// One prior exchange in the Home conversation, carried to intent resolution as
/// C-009 `history`. `role` is `user` or `assistant`.
@immutable
class IntentHistoryTurn {
  const IntentHistoryTurn({required this.role, required this.text});

  final String role;
  final String text;

  Map<String, dynamic> toJson() => {'role': role, 'text': text};
}

/// A resolved request from the assistant (CONTRACTS.md C-009).
///
/// The client renders confirmations from the machine-actionable intent, never
/// from raw text (FEAT-003/011). The user-facing message is the model-authored
/// [reply]; the intent carries only the fields the client acts on. Amounts are
/// integer minor units (kobo).
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
    this.detectedLanguage,
    this.reply,
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

  /// The language the model detected or served (`en`, `pcm`, `ha`, `yo`, `ig`),
  /// a machine-actionable signal the client consumes (MQ-001/MQ-004). Null when
  /// none was detected.
  final String? detectedLanguage;

  /// The model-authored user-facing message in the user's language: the
  /// greeting, the clarifying question, the refusal, or the non-resolving reply
  /// (screens/03-home.md). Null when the model produced none, so the client
  /// renders its prewritten fallback for the state.
  final String? reply;

  final List<ServiceSummary> candidates;

  /// `model` or `fallback`; a fallback resolution must be confirmed before any
  /// money moves.
  final String source;

  /// Whether a usable model reply was produced. A blank or whitespace-only
  /// reply is treated as absent so a turn is never left empty.
  bool get hasReply => reply != null && reply!.trim().isNotEmpty;

  /// Below the serving cutoff the model asks a follow-up question in [reply]
  /// and sets no payment type; the client asks it while the reply is present.
  /// A greeting never consumes a clarification turn, and a turn with no reply
  /// degrades to the keyword and search fallback (MQ-001).
  bool get needsClarification =>
      confidence < intentServingConfidenceCutoff &&
      !isNonCommand &&
      hasReply;

  /// A greeting, thanks, or small talk. Answered conversationally, never
  /// recorded as a coverage miss, and never counted as a clarification turn.
  bool get isNonCommand => intentType == intentTypeNonCommand;

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
      detectedLanguage:
          (json['detected_language'] ?? json['detectedLanguage'])?.toString(),
      reply: json['reply']?.toString(),
      candidates: candidates
          .whereType<Map>()
          .map((e) => ServiceSummary.fromJson(e.cast<String, dynamic>()))
          .toList(growable: false),
      source: (json['source'] ?? 'model').toString(),
    );
  }
}
