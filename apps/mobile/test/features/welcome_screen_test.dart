import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/welcome/welcome_screen.dart';

import '../helpers.dart';

void main() {
  testWidgets('default state states the value and offers the primary action', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const WelcomeScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) => MockAuthRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Say it. Pay it. Prove it.'), findsOneWidget);
    expect(find.text('Get started'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
  });

  testWidgets('checking capability shows a spinner on the action', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const WelcomeScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) =>
              MockAuthRepository(latency: const Duration(milliseconds: 200)),
        ),
      ],
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('a device without a passkey states the reduced security', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const WelcomeScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) => MockAuthRepository(
            passkeyAvailable: false,
            latency: Duration.zero,
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('This device can’t use a passkey'), findsOneWidget);
    expect(find.text('Create account with a recovery code'), findsOneWidget);
  });

  testWidgets('registration failure shows the error and preserves the action', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const WelcomeScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) =>
              MockAuthRepository(latency: Duration.zero, failNextCreate: true),
        ),
      ],
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Get started'));
    await tester.pumpAndSettle();
    expect(
      find.text('We couldn’t create your account. Nothing was saved.'),
      findsOneWidget,
    );
    expect(find.text('Get started'), findsOneWidget);
  });

  testWidgets('success shows the recovery code once and blocks until saved', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const WelcomeScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) => MockAuthRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Get started'));
    await tester.pumpAndSettle();
    expect(find.text('Save your recovery code'), findsOneWidget);
    expect(find.text('SABI-4F9K-2Q7M-88XD'), findsOneWidget);

    // The continue action is blocked until the code is acknowledged.
    final continueButton = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Continue'),
    );
    expect(continueButton.onPressed, isNull);

    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    final enabledButton = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Continue'),
    );
    expect(enabledButton.onPressed, isNotNull);
  });

  testWidgets('offline shows the banner and queues account creation', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const WelcomeScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) => MockAuthRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();
    expect(find.textContaining('You’re offline'), findsOneWidget);
    await tester.tap(find.text('Get started'));
    await tester.pumpAndSettle();
    // No account is created offline; the request is queued instead.
    expect(find.text('Save your recovery code'), findsNothing);
    expect(
      find.text(
        'Your request is queued and will send when you’re back online.',
      ),
      findsOneWidget,
    );
  });
}
