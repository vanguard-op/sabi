import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api_client.dart';
import 'api_config.dart';
import 'connectivity.dart';
import 'reauth.dart';
import 'session.dart';

/// The runtime configuration, read once from `--dart-define` build flags. The
/// default is the mock build: no socket is opened, so the demo and the widget
/// suites behave exactly as before (see [ApiConfig.fromEnvironment]).
final apiConfigProvider = Provider<ApiConfig>(
  (ref) => ApiConfig.fromEnvironment,
);

/// The session cookie jar. One instance is shared by the HTTP client (which
/// captures and resends the cookie) and the launch check (which restores it),
/// so both operate on the same session.
final sessionCookieStoreProvider = Provider<SessionCookieStore>(
  (ref) => SessionCookieStore(),
);

/// Session state for route guarding. It lives here, next to the HTTP client, so
/// the client's `401` handling can read it without a dependency back through the
/// repository providers. The router and screens import it via `data/providers`.
final sessionProvider = Provider<SessionStore>((ref) {
  final store = SessionStore();
  ref.onDispose(store.dispose);
  return store;
});

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
    sessionCookie: ref.watch(sessionCookieStoreProvider),
    onUnauthenticated: () {
      // Only a session that was live can expire mid-use. During the launch check
      // the status is still unknown, so a `401` there just means "no persisted
      // session" and must not raise the overlay over Welcome.
      if (ref.read(sessionProvider).isAuthenticated) {
        ref.read(reauthProvider.notifier).require();
      }
    },
    onUnreachable: () =>
        ref.read(connectivityProvider.notifier).setOnline(false),
  );
  ref.onDispose(client.close);
  return client;
});
