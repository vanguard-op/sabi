import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api_client.dart';
import 'api_config.dart';
import 'connectivity.dart';
import 'reauth.dart';

/// The runtime configuration, read once from `--dart-define` build flags. The
/// default is the mock build: no socket is opened, so the demo and the widget
/// suites behave exactly as before (see [ApiConfig.fromEnvironment]).
final apiConfigProvider = Provider<ApiConfig>((ref) => ApiConfig.fromEnvironment);

/// The shared HTTP client. Created lazily so a mock build never builds a
/// transport; disposed with the container so a hot restart drops the socket.
///
/// The client is the one place that sees every response, so session handling is
/// wired here rather than repeated in each repository: a `401` raises the shared
/// Re-authorisation flow, and a transport failure flips the offline state. Both
/// are read lazily inside the callback, so the dependency stays one-way.
final apiClientProvider = Provider<SabApiClient>((ref) {
  final client = SabApiClient(
    config: ref.watch(apiConfigProvider),
    onUnauthenticated: () => ref.read(reauthProvider.notifier).require(),
    onUnreachable: () =>
        ref.read(connectivityProvider.notifier).setOnline(false),
  );
  ref.onDispose(client.close);
  return client;
});
