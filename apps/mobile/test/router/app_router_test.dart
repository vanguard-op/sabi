import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/session.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/account/account_screen.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/features/receipts/receipts_screen.dart';
import 'package:sabi_mobile/features/welcome/welcome_screen.dart';
import 'package:sabi_mobile/router/app_router.dart';

import '../helpers.dart';

List<Override> _baseOverrides() => [
  authRepositoryProvider.overrideWith(
    (ref) => MockAuthRepository(latency: Duration.zero),
  ),
  catalogueRepositoryProvider.overrideWith(
    (ref) => MockCatalogueRepository(latency: Duration.zero),
  ),
  accountRepositoryProvider.overrideWith(
    (ref) => MockAccountRepository(latency: Duration.zero),
  ),
  receiptRepositoryProvider.overrideWith(
    (ref) => MockReceiptRepository(latency: Duration.zero),
  ),
];

void main() {
  testWidgets('an unauthenticated deep link falls back to Welcome', (
    tester,
  ) async {
    await pumpSabApp(tester, overrides: _baseOverrides());
    await tester.pumpAndSettle();
    containerOf(tester).read(routerProvider).go('/account');
    await tester.pumpAndSettle();
    expect(find.byType(WelcomeScreen), findsOneWidget);
    expect(find.byType(AccountScreen), findsNothing);
  });

  testWidgets('an authenticated app opens on Home inside the shell', (
    tester,
  ) async {
    await pumpSabApp(
      tester,
      overrides: [
        ..._baseOverrides(),
        sessionProvider.overrideWith((ref) {
          final store = SessionStore()..signIn();
          ref.onDispose(store.dispose);
          return store;
        }),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.byType(HomeScreen), findsOneWidget);
    expect(find.byType(BottomNavigationBar), findsOneWidget);
    expect(find.text('Home'), findsWidgets);
    expect(find.text('Receipts'), findsOneWidget);
    expect(find.text('Account'), findsOneWidget);
  });

  testWidgets('the shell selects Receipts and Account tabs', (tester) async {
    await pumpSabApp(
      tester,
      overrides: [
        ..._baseOverrides(),
        sessionProvider.overrideWith((ref) {
          final store = SessionStore()..signIn();
          ref.onDispose(store.dispose);
          return store;
        }),
      ],
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Receipts'));
    await tester.pumpAndSettle();
    expect(find.byType(ReceiptsScreen), findsOneWidget);
    await tester.tap(find.text('Account'));
    await tester.pumpAndSettle();
    expect(find.byType(AccountScreen), findsOneWidget);
  });

  testWidgets('a task-first surface pushes without the navigation shell', (
    tester,
  ) async {
    await pumpSabApp(
      tester,
      overrides: [
        ..._baseOverrides(),
        sessionProvider.overrideWith((ref) {
          final store = SessionStore()..signIn();
          ref.onDispose(store.dispose);
          return store;
        }),
      ],
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(routerProvider).go('/pay/svc_lagos_land_use');
    await tester.pumpAndSettle();
    expect(find.byType(BottomNavigationBar), findsNothing);
    expect(find.text('Coming soon'), findsOneWidget);
    expect(find.text('This part of Sabi isn’t available yet.'), findsOneWidget);
  });
}
