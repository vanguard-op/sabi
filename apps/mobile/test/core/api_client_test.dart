import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sabi_mobile/core/api_client.dart';
import 'package:sabi_mobile/core/api_config.dart';
import 'package:sabi_mobile/core/api_exception.dart';

const _config = ApiConfig(baseUrl: 'http://10.0.2.2:8000/v1');

/// A client that answers every request with one canned response.
class _StubClient extends http.BaseClient {
  _StubClient(this.statusCode, this.body, {this.throwError});

  final int statusCode;
  final String body;
  final Object? throwError;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (throwError != null) throw throwError!;
    final bytes = utf8.encode(body);
    return http.StreamedResponse(
      Stream.value(bytes),
      statusCode,
      headers: {'content-type': 'application/json'},
    );
  }
}

void main() {
  group('error envelope', () {
    test('a 400 maps to the envelope code and message', () async {
      final client = SabApiClient(
        config: _config,
        httpClient: _StubClient(
          400,
          jsonEncode({
            'error': {'code': 'invalid_request', 'message': 'Enter an amount.'},
          }),
        ),
      );
      await expectLater(
        client.get('/payments'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.statusCode, 'status', 400)
              .having((e) => e.code, 'code', 'invalid_request')
              .having((e) => e.message, 'message', 'Enter an amount.'),
        ),
      );
    });

    test('a non-JSON error body still yields an ApiException', () async {
      final client = SabApiClient(
        config: _config,
        httpClient: _StubClient(500, '<html>boom</html>'),
      );
      await expectLater(
        client.get('/payments'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', 'http_500')),
      );
    });
  });

  group('session and transport hooks', () {
    test('a 401 raises the re-authorisation hook and throws', () async {
      var reauth = 0;
      final client = SabApiClient(
        config: _config,
        httpClient: _StubClient(
          401,
          jsonEncode({
            'error': {'code': 'unauthenticated', 'message': 'Sign in.'},
          }),
        ),
        onUnauthenticated: () => reauth++,
      );
      await expectLater(
        client.get('/account/me'),
        throwsA(isA<ApiUnauthenticated>()),
      );
      expect(reauth, 1);
    });

    test('a transport failure raises the offline hook and throws', () async {
      var offline = 0;
      final client = SabApiClient(
        config: _config,
        httpClient: _StubClient(200, '{}', throwError: http.ClientException('no')),
        onUnreachable: () => offline++,
      );
      await expectLater(
        client.get('/account/me'),
        throwsA(isA<ApiUnreachable>()),
      );
      expect(offline, 1);
    });

    test('a timeout raises the offline hook', () async {
      var offline = 0;
      final client = SabApiClient(
        config: _config,
        httpClient: _StubClient(200, '{}', throwError: TimeoutException('slow')),
        onUnreachable: () => offline++,
      );
      await expectLater(
        client.get('/account/me'),
        throwsA(isA<ApiUnreachable>()),
      );
      expect(offline, 1);
    });
  });

  group('public auth endpoints opt out of the re-authorisation signal', () {
    const rejection = {
      'error': {'code': 'unauthenticated', 'message': 'No match.'},
    };

    test('C-004 login/verify 401 stays an inline credential error', () async {
      var reauth = 0;
      final client = SabApiClient(
        config: _config,
        httpClient: _StubClient(401, jsonEncode(rejection)),
        onUnauthenticated: () => reauth++,
      );
      await expectLater(
        client.post('/auth/login/verify', body: const {}),
        throwsA(isA<ApiUnauthenticated>()),
      );
      // The rejection is still thrown for the caller to map; only the shared
      // session-expiry signal is withheld.
      expect(reauth, 0);
    });

    test(
      'C-005 recovery/verify 401 stays an inline credential error',
      () async {
        var reauth = 0;
        final client = SabApiClient(
          config: _config,
          httpClient: _StubClient(401, jsonEncode(rejection)),
          onUnauthenticated: () => reauth++,
        );
        await expectLater(
          client.post('/auth/recovery/verify', body: const {}),
          throwsA(isA<ApiUnauthenticated>()),
        );
        expect(reauth, 0);
      },
    );

    test('an authenticated auth endpoint still raises the signal', () async {
      var reauth = 0;
      final client = SabApiClient(
        config: _config,
        httpClient: _StubClient(401, jsonEncode(rejection)),
        onUnauthenticated: () => reauth++,
      );
      await expectLater(
        client.post('/auth/channel-links', body: const {}),
        throwsA(isA<ApiUnauthenticated>()),
      );
      expect(reauth, 1);
    });
  });

  group('status preservation', () {
    test('getWithStatus keeps a 202 while get returns its body', () async {
      final client = SabApiClient(
        config: _config,
        httpClient: _StubClient(
          202,
          jsonEncode({'status': 'awaiting_receipt', 'retryAfterSeconds': 30}),
        ),
      );
      final response = await client.getWithStatus('/receipt');
      expect(response.statusCode, 202);
      expect(response.body['status'], 'awaiting_receipt');
    });

    test('the base URL joins the path under one /v1 prefix', () async {
      late Uri seen;
      final client = SabApiClient(
        config: _config,
        httpClient: _RecordingClient((uri) => seen = uri),
      );
      await client.get('/payments', query: {'limit': '20', 'cursor': null});
      expect(seen.toString(), 'http://10.0.2.2:8000/v1/payments?limit=20');
    });
  });
}

class _RecordingClient extends http.BaseClient {
  _RecordingClient(this.onSend);

  final void Function(Uri) onSend;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    onSend(request.url);
    return http.StreamedResponse(
      Stream.value(utf8.encode('{}')),
      200,
      headers: {'content-type': 'application/json'},
    );
  }
}
