import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_exception.dart';
import '../core/api_providers.dart';
import '../l10n/sab_strings.dart';
import 'http_auth_repository.dart';
import 'http_repositories.dart';
import 'mock_repositories.dart';
import 'repositories.dart';

// Session state is built beside the HTTP client, which reads it on a `401`; it
// is re-exported here because screens and the router already import this file
// for their providers.
export '../core/api_providers.dart' show sessionProvider;

/// Repository wiring. The mock is the default; the live HTTP implementations
/// are selected by the `USE_LIVE_REPOSITORIES` build flag, so the demo build and
/// the widget tests never open a socket. Screens depend on the abstractions,
/// never on the mock or the transport.
final authRepositoryProvider = Provider<AuthRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpAuthRepository(ref.watch(apiClientProvider));
  }
  return MockAuthRepository();
});

final catalogueRepositoryProvider = Provider<CatalogueRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpCatalogueRepository(ref.watch(apiClientProvider));
  }
  return MockCatalogueRepository();
});

final accountRepositoryProvider = Provider<AccountRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpAccountRepository(ref.watch(apiClientProvider));
  }
  return MockAccountRepository();
});

final receiptRepositoryProvider = Provider<ReceiptRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpReceiptRepository(ref.watch(apiClientProvider));
  }
  return MockReceiptRepository();
});

final receiptsRepositoryProvider = Provider<ReceiptsRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpReceiptsRepository(ref.watch(apiClientProvider));
  }
  return MockReceiptsRepository();
});

final casesRepositoryProvider = Provider<CasesRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpCasesRepository(ref.watch(apiClientProvider));
  }
  return MockCasesRepository();
});

/// Record lookup grounding (FEAT-023; user-flow Flow 9). Composed from the
/// receipt and case repositories so a lookup is always scoped to the owner's
/// records and never invents one.
final recordLookupRepositoryProvider = Provider<RecordLookupRepository>((ref) {
  final receipts = ref.watch(receiptsRepositoryProvider);
  final cases = ref.watch(casesRepositoryProvider);
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpRecordLookupRepository(receipts, cases);
  }
  return MockRecordLookupRepository(receipts: receipts, cases: cases);
});

/// Restores the persisted session cookie once at launch and verifies it with an
/// authenticated C-008 call, so the session is resolved before the router
/// chooses a destination and neither Welcome nor Home flashes. A 200 resolves
/// authenticated; no cookie, a definitive `401`, or an unreachable gateway
/// resolves unauthenticated (the HTTP client clears a rejected cookie itself).
final sessionBootstrapProvider = FutureProvider<void>((ref) async {
  final session = ref.read(sessionProvider);
  // A session already resolved in-process (a sign-in beat the launch check, or
  // a test provided one) needs no restore.
  if (!session.isUnresolved) return;

  final cookies = ref.read(sessionCookieStoreProvider);
  await cookies.load();
  if (!cookies.hasSession) {
    session.resolveUnauthenticated();
    return;
  }

  try {
    await ref.read(accountRepositoryProvider).me();
    session.resolveAuthenticated();
  } on ApiUnauthenticated {
    // The stored session is dead: clear it and stay signed out. The HTTP client
    // clears too; doing it here keeps the guarantee if the call is stubbed.
    await cookies.clear();
    session.resolveUnauthenticated();
  } on ApiUnreachable {
    // No network at launch: start signed out and keep the cookie for a later
    // launch. Never hold the first screen on an unverifiable session.
    session.resolveUnauthenticated();
  }
});

/// The locale used when a mock or fallback needs one outside a widget.
final activeLocaleProvider = Provider<AppLocale>(
  (ref) => ref.watch(localeProvider),
);
