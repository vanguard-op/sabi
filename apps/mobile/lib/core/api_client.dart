import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_config.dart';
import 'api_exception.dart';

/// A thin JSON client over the API gateway (architecture.md "API Gateway /
/// Backend-for-Frontend").
///
/// Responsibilities kept deliberately narrow:
/// - Builds `/v1` URLs from [ApiConfig.baseUrl].
/// - Sends and receives JSON with camelCase fields.
/// - Carries the session as the platform cookie jar: `dart:io` / the browser
///   persist `Set-Cookie` and resend it, and [http.Client] uses that jar, so the
///   HttpOnly session cookie from C-002/C-004 is neither read nor stored in
///   Dart code. The client never logs a request/response body or header.
/// - Maps the shared error envelope to [ApiException] and treats a transport
///   failure as [ApiUnreachable].
class SabApiClient {
  SabApiClient({
    required ApiConfig config,
    http.Client? httpClient,
    this.onUnauthenticated,
    this.onUnreachable,
  })
    // A named parameter cannot be private, so the config is copied to the
    // private field rather than promoted to a public one.
    // ignore: prefer_initializing_formals
    : _config = config,
      _http = httpClient ?? http.Client();

  final ApiConfig _config;
  final http.Client _http;

  /// Called once when the gateway rejects the session cookie, before
  /// [ApiUnauthenticated] is thrown. The client raises the shared
  /// Re-authorisation flow; it does not know about Riverpod itself.
  final void Function()? onUnauthenticated;

  /// Called once when the gateway cannot be reached at all, before
  /// [ApiUnreachable] is thrown, so the surface can flip to its offline states.
  final void Function()? onUnreachable;

  Uri _uri(String path, [Map<String, String?> query = const {}]) {
    final cleaned = path.startsWith('/') ? path.substring(1) : path;
    final base = _config.baseUrl.endsWith('/')
        ? _config.baseUrl.substring(0, _config.baseUrl.length - 1)
        : _config.baseUrl;
    final uri = Uri.parse('$base/$cleaned');
    final filtered = <String, String>{
      for (final entry in query.entries)
        if (entry.value != null) entry.key: entry.value!,
    };
    return filtered.isEmpty ? uri : uri.replace(queryParameters: filtered);
  }

  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String?> query = const {},
  }) => _send('GET', path, query: query).then((r) => r.body);

  Future<Map<String, dynamic>> post(
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) => _send('POST', path, body: body, headers: headers).then((r) => r.body);

  /// Like [get] but keeps the status code, for the endpoints where a `202` is a
  /// distinct, valid state rather than a success body (C-031 FTeR, C-035 token).
  Future<ApiResponse> getWithStatus(
    String path, {
    Map<String, String?> query = const {},
  }) => _send('GET', path, query: query);

  Future<ApiResponse> _send(
    String method,
    String path, {
    Map<String, String?> query = const {},
    Object? body,
    Map<String, String>? headers,
  }) async {
    final uri = _uri(path, query);
    final requestHeaders = <String, String>{
      'accept': 'application/json',
      if (body != null) 'content-type': 'application/json',
      ...?headers,
    };

    http.Response response;
    try {
      final request = http.Request(method, uri)..headers.addAll(requestHeaders);
      if (body != null) request.body = jsonEncode(body);
      final streamed = await _http
          .send(request)
          .timeout(const Duration(seconds: 20));
      response = await http.Response.fromStream(streamed);
    } on TimeoutException catch (error) {
      onUnreachable?.call();
      throw ApiUnreachable(error);
    } on http.ClientException catch (error) {
      onUnreachable?.call();
      throw ApiUnreachable(error);
    } on Exception catch (error) {
      // dart:io SocketException is not a ClientException; catch it generically
      // rather than let a transport failure escape as an unhandled exception.
      onUnreachable?.call();
      throw ApiUnreachable(error);
    }

    return _decode(response);
  }

  ApiResponse _decode(http.Response response) {
    final status = response.statusCode;
    Map<String, dynamic>? decoded;
    if (response.body.isNotEmpty) {
      try {
        final value = jsonDecode(response.body);
        if (value is Map<String, dynamic>) decoded = value;
      } on FormatException {
        decoded = null;
      }
    }

    if (status >= 200 && status < 300) {
      return ApiResponse(
        statusCode: status,
        body: decoded ?? const <String, dynamic>{},
      );
    }

    final envelope = decoded?['error'];
    final code = envelope is Map && envelope['code'] is String
        ? envelope['code'] as String
        : 'http_$status';
    final rawMessage = envelope is Map && envelope['message'] is String
        ? envelope['message'] as String
        : _defaultMessage(status);
    final details = envelope is Map ? envelope['details'] : null;

    if (status == 401) {
      // The session cookie is absent or rejected: raise the shared
      // Re-authorisation flow rather than a bare error (user-flow
      // "Authentication Gate").
      onUnauthenticated?.call();
      throw ApiUnauthenticated(code: code, message: rawMessage, details: details);
    }
    if (status == 403) {
      throw ApiForbidden(code: code, message: rawMessage, details: details);
    }
    if (status == 404) {
      throw ApiNotFound(code: code, message: rawMessage, details: details);
    }
    if (status == 409) {
      throw ApiConflict(code: code, message: rawMessage, details: details);
    }
    throw ApiException(
      statusCode: status,
      code: code,
      message: rawMessage,
      details: details,
    );
  }

  static String _defaultMessage(int status) => switch (status) {
    400 => 'The request is not valid.',
    401 => 'Sign in to continue.',
    403 => 'You do not have access to this.',
    404 => 'We could not find that.',
    409 => 'That conflicts with the current state.',
    410 => 'That has expired. Start again.',
    422 => 'Check the details and try again.',
    429 => 'Too many attempts. Try again shortly.',
    500 => 'Something went wrong on our side.',
    503 => 'That service is unavailable right now.',
    _ => 'The request failed.',
  };

  void close() => _http.close();
}

/// A 2xx response with its status kept, so a caller can tell an accepted `202`
/// from a `200` with a body (C-031, C-035).
class ApiResponse {
  const ApiResponse({required this.statusCode, required this.body});

  final int statusCode;
  final Map<String, dynamic> body;
}
