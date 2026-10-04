import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sabi_mobile/core/api_client.dart';
import 'package:sabi_mobile/core/api_config.dart';
import 'package:sabi_mobile/core/api_exception.dart';
import 'package:sabi_mobile/core/session.dart';

const _config = ApiConfig(baseUrl: 'http://10.0.2.2:8000/v1');
const _sessionCookie =
    'sabi_session=tok.abc.123; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax; Secure';

class _MemoryStorage implements SessionCookieStorage {
  String? value;
  bool failRead = false;

  @override
  Future<String?> read() async {
    if (failRead) throw StateError('keystore unavailable');
    return value;
  }

  @override
  Future<void> write(String value) async => this.value = value;

  @override
  Future<void> clear() async => value = null;
}

/// Answers every request with one canned response and records the requests it
/// saw, so a test can assert the cookie on the wire.
class _RecordingClient extends http.BaseClient {
  _RecordingClient({
    this.statusCode = 200,
    this.body = '{}',
    this.responseHeaders = const {},
  });

  final int statusCode;
  final String body;
  final Map<String, String> responseHeaders;
  final List<http.BaseRequest> requests = [];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    return http.StreamedResponse(
      Stream.value(utf8.encode(body)),
      statusCode,
      headers: {'content-type': 'application/json', ...responseHeaders},
    );
  }
}

void main() {
  test(
    'a session Set-Cookie is captured and sent on the next request',
    () async {
      final storage = _MemoryStorage();
      final store = SessionCookieStore(storage: storage);
      final httpClient = _RecordingClient(
        responseHeaders: {'set-cookie': _sessionCookie},
      );
      final client = SabApiClient(
        config: _config,
        httpClient: httpClient,
        sessionCookie: store,
      );

      await client.post('/auth/login/verify', body: const {});
      expect(store.hasSession, isTrue);
      expect(httpClient.requests.first.headers['cookie'], isNull);

      await client.get('/account/me');
      expect(
        httpClient.requests.last.headers['cookie'],
        'sabi_session=tok.abc.123',
      );
    },
  );

  test('a persisted cookie is restored before the first request', () async {
    final storage = _MemoryStorage()..value = 'restored.token';
    final store = SessionCookieStore(storage: storage);
    final httpClient = _RecordingClient();
    final client = SabApiClient(
      config: _config,
      httpClient: httpClient,
      sessionCookie: store,
    );

    await client.get('/account/me');

    expect(
      httpClient.requests.single.headers['cookie'],
      'sabi_session=restored.token',
    );
  });

  test(
    'a definitive 401 clears the cookie and raises reauthorisation',
    () async {
      final storage = _MemoryStorage()..value = 'dead.token';
      final store = SessionCookieStore(storage: storage);
      var reauth = 0;
      final client = SabApiClient(
        config: _config,
        httpClient: _RecordingClient(
          statusCode: 401,
          body: jsonEncode({
            'error': {'code': 'unauthenticated', 'message': 'Sign in.'},
          }),
        ),
        sessionCookie: store,
        onUnauthenticated: () => reauth++,
      );

      await expectLater(
        client.get('/account/me'),
        throwsA(isA<ApiUnauthenticated>()),
      );

      expect(store.hasSession, isFalse);
      expect(storage.value, isNull);
      expect(reauth, 1);
    },
  );

  test(
    'a 401 on a public auth path keeps the cookie and stays silent',
    () async {
      final storage = _MemoryStorage()..value = 'held.token';
      final store = SessionCookieStore(storage: storage);
      var reauth = 0;
      final client = SabApiClient(
        config: _config,
        httpClient: _RecordingClient(
          statusCode: 401,
          body: jsonEncode({
            'error': {'code': 'unauthenticated', 'message': 'No match.'},
          }),
        ),
        sessionCookie: store,
        onUnauthenticated: () => reauth++,
      );

      await expectLater(
        client.post('/auth/login/verify', body: const {}),
        throwsA(isA<ApiUnauthenticated>()),
      );

      // The sign-in 401 is a credential outcome, not a dead session; the cookie
      // is untouched and the shared overlay is not raised.
      expect(store.hasSession, isTrue);
      expect(reauth, 0);
    },
  );

  test('sign-out clears the persisted cookie', () async {
    final storage = _MemoryStorage()..value = 'live.token';
    final store = SessionCookieStore(storage: storage);
    final client = SabApiClient(
      config: _config,
      httpClient: _RecordingClient(),
      sessionCookie: store,
    );

    await client.clearSession();

    expect(store.hasSession, isFalse);
    expect(storage.value, isNull);
  });
}
