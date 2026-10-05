import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/session.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/account/account_screen.dart';
import 'package:sabi_mobile/features/account/verification/verification_screen.dart';
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

/// A resolved session, so the router does not touch platform storage.
Override _session({required bool authenticated}) =>
    sessionProvider.overrideWith((ref) {
      final store = SessionStore();
      if (authenticated) {
        store.signIn();
      } else {
        store.signOut();
      }
      ref.onDispose(store.dispose);
      return store;
    });

// The launch check is a no-op once the session is already resolved, which every
// test here provides through [_session].
final _noopBootstrap = sessionBootstrapProvider.overrideWith((ref) {});

void main() {
  testWidgets('an unauthenticated deep link falls back to Welcome', (
    tester,
  ) async {
    await pumpSabApp(
      tester,
      overrides: [
        ..._baseOverrides(),
        _session(authenticated: false),
        _noopBootstrap,
      ],
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(routerProvider).go('/account');
    await tester.pumpAndSettle();
    expect(find.byType(WelcomeScreen), findsOneWidget);
    expect(find.byType(AccountScreen), findsNothing);
  });

  testWidgets('the app holds on the splash while the session is unresolved', (
    tester,
  ) async {
    final pending = Completer<void>();
    final store = SessionStore();
    await pumpSabApp(
      tester,
      overrides: [
        ..._baseOverrides(),
        sessionProvider.overrideWithValue(store),
        sessionBootstrapProvider.overrideWith((ref) => pending.future),
      ],
    );
    await tester.pump();
    expect(find.byKey(const ValueKey('startup')), findsOneWidget);
    expect(find.byType(WelcomeScreen), findsNothing);
    expect(find.byType(HomeScreen), findsNothing);

    store.resolveUnauthenticated();
    pending.complete();
    await tester.pumpAndSettle();
    expect(find.byType(WelcomeScreen), findsOneWidget);
  });

  testWidgets('a resolved launch check replaces the splash with Home', (
    tester,
  ) async {
    final store = SessionStore();
    await pumpSabApp(
      tester,
      overrides: [
        ..._baseOverrides(),
        sessionProvider.overrideWithValue(store),
        sessionBootstrapProvider.overrideWith(
          (ref) => store.resolveAuthenticated(),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.byType(HomeScreen), findsOneWidget);
    expect(find.byKey(const ValueKey('startup')), findsNothing);
  });

  testWidgets('an authenticated app opens on Home inside the shell', (
    tester,
  ) async {
    await pumpSabApp(
      tester,
      overrides: [
        ..._baseOverrides(),
        _session(authenticated: true),
        _noopBootstrap,
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
        _session(authenticated: true),
        _noopBootstrap,
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
        _session(authenticated: true),
        _noopBootstrap,
      ],
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(routerProvider).go('/account/verify');
    await tester.pumpAndSettle();
    // The identity surface renders above the shell rather than the gated
    // placeholder, so the task-first push stays shell-free.
    expect(find.byType(BottomNavigationBar), findsNothing);
    expect(find.byType(VerificationScreen), findsOneWidget);
  });

  testWidgets('no payment route remains, so nothing reaches a deleted screen', (
    tester,
  ) async {
    await pumpSabApp(
      tester,
      overrides: [
        ..._baseOverrides(),
        _session(authenticated: true),
        _noopBootstrap,
      ],
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(routerProvider).go('/pay/svc_lagos_land_use');
    await tester.pumpAndSettle();
    // Payment completes inline in the conversation; the old confirmation route
    // is gone and resolves to the router's not-found surface instead.
    expect(find.byType(HomeScreen), findsNothing);
    expect(find.byType(VerificationScreen), findsNothing);
    expect(find.text('Sabi'), findsOneWidget);
  });
}
