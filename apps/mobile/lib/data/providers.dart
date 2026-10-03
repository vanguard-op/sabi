import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_providers.dart';
import '../core/session.dart';
import '../l10n/sab_strings.dart';
import 'http_auth_repository.dart';
import 'http_repositories.dart';
import 'mock_repositories.dart';
import 'repositories.dart';

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

/// The app session, shared by the router and the screens.
final sessionProvider = Provider<SessionStore>((ref) {
  final store = SessionStore();
  ref.onDispose(store.dispose);
  return store;
});

/// The locale used when a mock or fallback needs one outside a widget.
final activeLocaleProvider = Provider<AppLocale>(
  (ref) => ref.watch(localeProvider),
);
