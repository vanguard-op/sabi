import 'package:flutter/foundation.dart';

/// Runtime configuration for the live client.
///
/// Values arrive as `--dart-define` build flags so one binary can point at a
/// local emulator, a staging gateway, or production without a code change. There
/// are no secrets in the mobile client (NFR-024): the base URL is not
/// confidential, and the session lives in an HttpOnly cookie the client never
/// reads or logs.
@immutable
class ApiConfig {
  const ApiConfig({required this.baseUrl, this.useLiveRepositories = false});

  /// Base URL of the API gateway (architecture.md "API Gateway /
  /// Backend-for-Frontend"), including the `/v1` path prefix, with no trailing
  /// slash. The Android emulator reaches the host at `10.0.2.2`, so a local run
  /// passes `--dart-define=API_BASE_URL=http://10.0.2.2:8000/v1`.
  final String baseUrl;

  /// Whether repository providers resolve to the live HTTP implementations.
  /// False (the default) keeps the in-memory mocks, so tests and the demo build
  /// never open a socket.
  final bool useLiveRepositories;

  /// Compile-time defaults. `USE_LIVE_REPOSITORIES` is the explicit switch for
  /// live vs mock; the route's "build flag (or an equivalent explicit switch)".
  static const ApiConfig fromEnvironment = ApiConfig(
    baseUrl: String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: 'http://localhost:8000/v1',
    ),
    useLiveRepositories: bool.fromEnvironment('USE_LIVE_REPOSITORIES'),
  );

  ApiConfig copyWith({String? baseUrl, bool? useLiveRepositories}) => ApiConfig(
    baseUrl: baseUrl ?? this.baseUrl,
    useLiveRepositories: useLiveRepositories ?? this.useLiveRepositories,
  );

  @override
  bool operator ==(Object other) =>
      other is ApiConfig &&
      other.baseUrl == baseUrl &&
      other.useLiveRepositories == useLiveRepositories;

  @override
  int get hashCode => Object.hash(baseUrl, useLiveRepositories);
}
