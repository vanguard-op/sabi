import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/session.dart';
import '../l10n/sab_strings.dart';
import 'mock_repositories.dart';
import 'repositories.dart';

/// Repository wiring. Swapped for live implementations when the endpoints land;
/// screens depend on the abstractions, never on the mock.
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => MockAuthRepository(),
);

final catalogueRepositoryProvider = Provider<CatalogueRepository>(
  (ref) => MockCatalogueRepository(),
);

final accountRepositoryProvider = Provider<AccountRepository>(
  (ref) => MockAccountRepository(),
);

final receiptRepositoryProvider = Provider<ReceiptRepository>(
  (ref) => MockReceiptRepository(),
);

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
