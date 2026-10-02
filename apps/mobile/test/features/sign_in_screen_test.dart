import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/sign_in/sign_in_screen.dart';

import '../helpers.dart';

void main() {
  testWidgets('default offers the passkey action and its alternatives', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const SignInScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) => MockAuthRepository(latency: Duration.zero),
        ),
      ],
    );
    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.text('Continue with passkey'), findsOneWidget);
    expect(find.text('Use a recovery code'), findsOneWidget);
    expect(find.text('Create an account'), findsOneWidget);
  });

  testWidgets('recovery route reveals the code entry in place', (tester) async {
    await pumpSab(
      tester,
      const SignInScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) => MockAuthRepository(latency: Duration.zero),
        ),
      ],
    );
    expect(find.text('Recovery code'), findsNothing);
    await tester.tap(find.text('Use a recovery code'));
    await tester.pumpAndSettle();
    expect(find.text('Recovery code'), findsOneWidget);
    expect(find.text('Sign in with code'), findsOneWidget);
  });

  testWidgets('an empty recovery code reports the required-field error', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const SignInScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) => MockAuthRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.tap(find.text('Use a recovery code'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign in with code'));
    await tester.pumpAndSettle();
    expect(find.text('This is needed'), findsOneWidget);
  });

  testWidgets('a rejected recovery code shows an inline reason', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const SignInScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) => MockAuthRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.tap(find.text('Use a recovery code'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'short');
    await tester.tap(find.text('Sign in with code'));
    await tester.pumpAndSettle();
    expect(
      find.text('That didn’t match. Check the code and try again.'),
      findsOneWidget,
    );
  });

  testWidgets('a rejected passkey shows the retry reason without a session', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const SignInScreen(),
      overrides: [
        authRepositoryProvider.overrideWith(
          (ref) =>
              MockAuthRepository(latency: Duration.zero, failNextSignIn: true),
        ),
      ],
    );
    await tester.tap(find.text('Continue with passkey'));
    await tester.pumpAndSettle();
    expect(
      find.text(
        'The passkey wasn’t accepted. Try again or use a recovery code.',
      ),
      findsOneWidget,
    );
    expect(find.text('Continue with passkey'), findsOneWidget);
  });

  testWidgets(
    'the account is stated unrecoverable when both credentials are lost',
    (tester) async {
      await pumpSab(
        tester,
        const SignInScreen(),
        overrides: [
          authRepositoryProvider.overrideWith(
            (ref) => MockAuthRepository(latency: Duration.zero),
          ),
        ],
      );
      expect(
        find.textContaining('this account can’t be recovered'),
        findsOneWidget,
      );
    },
  );
}
