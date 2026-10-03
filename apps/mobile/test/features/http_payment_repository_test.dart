import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sabi_mobile/core/api_client.dart';
import 'package:sabi_mobile/core/api_config.dart';
import 'package:sabi_mobile/features/payment/data/http_payment_repository.dart';
import 'package:sabi_mobile/features/payment/models/payment.dart';
import 'package:sabi_mobile/features/payment/models/payment_errors.dart';

const _config = ApiConfig(baseUrl: 'http://10.0.2.2:8000/v1');

class _StubClient extends http.BaseClient {
  _StubClient(this.statusCode, this.body);

  final int statusCode;
  final String body;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    return http.StreamedResponse(
      Stream.value(utf8.encode(body)),
      statusCode,
      headers: {'content-type': 'application/json'},
    );
  }
}

SabApiClient _api(int status, Object body) =>
    SabApiClient(config: _config, httpClient: _StubClient(status, jsonEncode(body)));

void main() {
  group('authorise (C-017)', () {
    test('a 201 parses the mandate', () async {
      final repo = HttpPaymentRepository(
        _api(201, {
          'paymentId': 'pay_1',
          'status': 'initiated',
          'mandateId': 'mnd_1',
          'railReference': null,
        }),
      );
      final result = await repo.authorise(serviceId: 'svc', amount: 100);
      expect(result.paymentId, 'pay_1');
      expect(result.status, PaymentState.initiated);
    });

    test('a 422 asks for the second confirmation, not a generic failure', () {
      final repo = HttpPaymentRepository(_api(422, {
        'error': {'code': 'validation_failed', 'message': 'Above your limit.'},
      }));
      expect(
        () => repo.authorise(serviceId: 'svc', amount: 99999999),
        throwsA(isA<SecondConfirmationRequiredException>()),
      );
    });

    test('a 402 is insufficient funds', () {
      final repo = HttpPaymentRepository(_api(402, {
        'error': {'code': 'payment_required', 'message': 'Not enough.'},
      }));
      expect(
        () => repo.authorise(serviceId: 'svc', amount: 100),
        throwsA(isA<InsufficientFundsException>()),
      );
    });

    test('a 409 carries the existing payment from details', () async {
      final repo = HttpPaymentRepository(_api(409, {
        'error': {
          'code': 'conflict',
          'message': 'Already received.',
          'details': {'paymentId': 'pay_existing', 'railReference': 'RAIL-1'},
        },
      }));
      try {
        await repo.authorise(serviceId: 'svc', amount: 100);
        fail('expected a duplicate authorisation');
      } on DuplicateAuthorisationException catch (e) {
        expect(e.paymentId, 'pay_existing');
        expect(e.railReference, 'RAIL-1');
      }
    });
  });

  group('execute (C-018)', () {
    test('a 410 is an expired mandate', () {
      final repo = HttpPaymentRepository(_api(410, {
        'error': {'code': 'challenge_expired', 'message': 'Expired.'},
      }));
      expect(
        () => repo.execute(paymentId: 'pay_1', mandateId: 'mnd_1'),
        throwsA(isA<MandateExpiredException>()),
      );
    });

    test('a 422 is a mandate mismatch', () {
      final repo = HttpPaymentRepository(_api(422, {
        'error': {'code': 'validation_failed', 'message': 'Changed.'},
      }));
      expect(
        () => repo.execute(paymentId: 'pay_1', mandateId: 'mnd_1'),
        throwsA(isA<MandateMismatchException>()),
      );
    });
  });

  group('federal (C-030, C-031)', () {
    test('a 409 re-resolves the collection account', () {
      final repo = HttpFederalRepository(_api(409, {
        'error': {'code': 'conflict', 'message': 'Changed.'},
      }));
      expect(
        () => repo.prepare(serviceId: 'svc'),
        throwsA(isA<CollectionAccountChangedException>()),
      );
    });

    test('a 422 is not a federal service', () {
      final repo = HttpFederalRepository(_api(422, {
        'error': {'code': 'validation_failed', 'message': 'Not federal.'},
      }));
      expect(
        () => repo.prepare(serviceId: 'svc'),
        throwsA(isA<InvalidFederalServiceException>()),
      );
    });

    test('a 202 receipt is an awaiting hold, not an error', () async {
      final repo = HttpFederalRepository(
        _api(202, {'status': 'awaiting_receipt', 'retryAfterSeconds': 30}),
      );
      final receipt = await repo.receipt('pay_1');
      expect(receipt.isAwaiting, isTrue);
    });

    test('a 409 receipt is not settled', () {
      final repo = HttpFederalRepository(_api(409, {
        'error': {'code': 'conflict', 'message': 'Not settled.'},
      }));
      expect(
        () => repo.receipt('pay_1'),
        throwsA(isA<FederalNotSettledException>()),
      );
    });
  });

  group('bills (C-033–C-035)', () {
    test('a 503 validation is the biller offline', () {
      final repo = HttpBillRepository(_api(503, {
        'error': {'code': 'biller_unavailable', 'message': 'Offline.'},
      }));
      expect(
        () => repo.validate(serviceId: 'svc', recipientIdentifier: '123'),
        throwsA(isA<BillerOfflineException>()),
      );
    });

    test('a 400 validation is an invalid recipient', () {
      final repo = HttpBillRepository(_api(400, {
        'error': {'code': 'invalid_request', 'message': 'Bad.'},
      }));
      expect(
        () => repo.validate(serviceId: 'svc', recipientIdentifier: ''),
        throwsA(isA<InvalidBillException>()),
      );
    });

    test('a 402 payment is insufficient funds', () {
      final repo = HttpBillRepository(_api(402, {
        'error': {'code': 'payment_required', 'message': 'Not enough.'},
      }));
      expect(
        () => repo.pay(serviceId: 'svc', recipientIdentifier: '123', amount: 100),
        throwsA(isA<BillInsufficientFundsException>()),
      );
    });

    test('a 202 token is an awaiting hold, not an error', () async {
      final repo = HttpBillRepository(
        _api(202, {'status': 'awaiting_token', 'retryAfterSeconds': 3}),
      );
      final token = await repo.token('pay_1');
      expect(token.isAwaiting, isTrue);
    });

    test('a 200 token carries the token and its receipt', () async {
      final repo = HttpBillRepository(
        _api(200, {'token': 'TOKEN-1', 'receiptId': 'rcp_1'}),
      );
      final token = await repo.token('pay_1');
      expect(token.isAwaiting, isFalse);
      expect(token.token, 'TOKEN-1');
      expect(token.receiptId, 'rcp_1');
    });

    test('a 409 token is a failed payment, never an awaiting hold', () async {
      final repo = HttpBillRepository(
        _api(409, {
          'error': {
            'code': 'payment_failed',
            'message': 'The biller rejected it.',
            'details': {'status': 'failed', 'reason': 'The meter was rejected.'},
          },
        }),
      );
      try {
        await repo.token('pay_1');
        fail('expected a failed-token exception');
      } on BillTokenFailedException catch (e) {
        expect(e.message, contains('The meter was rejected.'));
      }
    });

    test('a 409 token without a reason uses the surface wording', () async {
      final repo = HttpBillRepository(
        _api(409, {
          'error': {'code': 'payment_failed', 'message': 'Failed.'},
        }),
      );
      expect(
        () => repo.token('pay_1'),
        throwsA(
          isA<BillTokenFailedException>().having(
            (e) => e.message,
            'message',
            contains('no token was issued'),
          ),
        ),
      );
    });

    test('a 404 token is unknown', () {
      final repo = HttpBillRepository(_api(404, {
        'error': {'code': 'not_found', 'message': 'Unknown.'},
      }));
      expect(
        () => repo.token('pay_1'),
        throwsA(isA<BillTokenNotFoundException>()),
      );
    });
  });
}
