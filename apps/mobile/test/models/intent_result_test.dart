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

  group('IntentResult.isNonCommand', () {
    test('a non_command intent is recognised from either wire key', () {
      expect(
        IntentResult.fromJson({'intent_type': 'non_command'}).isNonCommand,
        isTrue,
      );
      expect(
        IntentResult.fromJson({'intentType': 'non_command'}).isNonCommand,
        isTrue,
      );
    });

    test('an ordinary intent is not a non-command', () {
      expect(
        IntentResult.fromJson({'intentType': 'gov_payment'}).isNonCommand,
        isFalse,
      );
      expect(
        IntentResult.fromJson({'intentType': 'unknown'}).isNonCommand,
        isFalse,
      );
    });

    test('a non-command never asks a clarifying question', () {
      final intent = IntentResult.fromJson({
        'intentType': 'non_command',
        'confidence': 0.1,
      });
      expect(intent.needsClarification, isFalse);
    });
  });

  group('IntentHistoryTurn', () {
    test('serialises as the contract {role, text} shape', () {
      const turn = IntentHistoryTurn(role: 'user', text: 'pay my rent');
      expect(turn.toJson(), {'role': 'user', 'text': 'pay my rent'});
    });

    test('the history bound is six entries', () {
      expect(intentHistoryMaxEntries, 6);
    });
  });
}
