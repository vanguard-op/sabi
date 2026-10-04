import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/models/intent_result.dart';

IntentResult _intent(double confidence, {String? question}) => IntentResult(
  intentType: 'unknown',
  confidence: confidence,
  clarifyingQuestion: question,
);

void main() {
  group('IntentResult.needsClarification', () {
    test('a question below the 0.70 serving cutoff asks it', () {
      expect(_intent(0.69, question: 'Which one?').needsClarification, isTrue);
    });

    test('the former 0.6 cutoff is no longer the bar', () {
      expect(_intent(0.6, question: 'Which one?').needsClarification, isTrue);
      expect(_intent(0.65, question: 'Which one?').needsClarification, isTrue);
    });

    test('at or above the cutoff a question does not ask', () {
      expect(_intent(0.70, question: 'Which one?').needsClarification, isFalse);
      expect(_intent(0.95, question: 'Which one?').needsClarification, isFalse);
    });

    test('without a question the confidence never asks one', () {
      expect(_intent(0.1).needsClarification, isFalse);
      expect(_intent(0.1, question: '').needsClarification, isFalse);
      expect(_intent(0.6, question: '').needsClarification, isFalse);
    });

    test('the serving cutoff is 0.70', () {
      expect(intentServingConfidenceCutoff, 0.70);
    });
  });
}
