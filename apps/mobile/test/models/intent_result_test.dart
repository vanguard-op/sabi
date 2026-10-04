import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/models/intent_result.dart';

IntentResult _intent(double confidence, {String? reply}) => IntentResult(
  intentType: 'unknown',
  confidence: confidence,
  reply: reply,
);

void main() {
  group('IntentResult.needsClarification', () {
    test('a reply below the 0.70 serving cutoff asks it', () {
      expect(_intent(0.69, reply: 'Which one?').needsClarification, isTrue);
    });

    test('the former 0.6 cutoff is no longer the bar', () {
      expect(_intent(0.6, reply: 'Which one?').needsClarification, isTrue);
      expect(_intent(0.65, reply: 'Which one?').needsClarification, isTrue);
    });

    test('at or above the cutoff a reply does not ask', () {
      expect(_intent(0.70, reply: 'Which one?').needsClarification, isFalse);
      expect(_intent(0.95, reply: 'Which one?').needsClarification, isFalse);
    });

    test('without a reply the confidence never asks one', () {
      expect(_intent(0.1).needsClarification, isFalse);
      expect(_intent(0.1, reply: '').needsClarification, isFalse);
      expect(_intent(0.6, reply: '   ').needsClarification, isFalse);
    });

    test('the serving cutoff is 0.70', () {
      expect(intentServingConfidenceCutoff, 0.70);
    });
  });

  group('IntentResult reply and language', () {
    test('the top-level reply is read as the model-authored message', () {
      final intent = IntentResult.fromJson({
        'intentType': 'unknown',
        'confidence': 0.5,
        'reply': 'Which biller do you mean?',
      });
      expect(intent.reply, 'Which biller do you mean?');
      expect(intent.hasReply, isTrue);
    });

    test('a null or blank reply is treated as absent', () {
      expect(IntentResult.fromJson({'reply': null}).hasReply, isFalse);
      expect(IntentResult.fromJson({'reply': '  '}).hasReply, isFalse);
      expect(IntentResult.fromJson(const {}).hasReply, isFalse);
    });

    test('detectedLanguage is read from either wire key', () {
      expect(
        IntentResult.fromJson({'detectedLanguage': 'pcm'}).detectedLanguage,
        'pcm',
      );
      expect(
        IntentResult.fromJson({'detected_language': 'yo'}).detectedLanguage,
        'yo',
      );
      expect(IntentResult.fromJson(const {}).detectedLanguage, isNull);
    });

    test('the removed language and clarifyingQuestion fields are not read', () {
      // C-009 revision 4 removed both; older wire keys must be ignored rather
      // than resurrected, so the model never reads a stale question.
      final intent = IntentResult.fromJson({
        'language': 'pcm',
        'clarifyingQuestion': 'A stale question?',
      });
      expect(intent.detectedLanguage, isNull);
      expect(intent.reply, isNull);
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

    test('a non-command with a reply never asks a clarifying question', () {
      final intent = IntentResult.fromJson({
        'intentType': 'non_command',
        'confidence': 0.1,
        'reply': 'I can pay bills for you.',
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
