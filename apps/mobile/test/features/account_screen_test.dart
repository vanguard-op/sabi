import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/skeleton.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/account/account_screen.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/account.dart';
import 'package:sabi_mobile/models/payment_method.dart';

import '../helpers.dart';

class _FailingAccountRepository extends MockAccountRepository {
  _FailingAccountRepository() : super(latency: Duration.zero);

  @override
  Future<Account> me() async => throw Exception('transport down');
}

void main() {
  testWidgets('loading shows a skeleton', (tester) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) =>
              MockAccountRepository(latency: const Duration(milliseconds: 200)),
        ),
      ],
    );
    await tester.pump();
    expect(find.byType(SabSkeletonList), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.byType(SabSkeletonList), findsNothing);
  });

  testWidgets('unverified makes verification the primary action', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) => MockAccountRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Not verified'), findsOneWidget);
    expect(find.text('Verify identity'), findsOneWidget);
    expect(find.text('Ngozi'), findsOneWidget);
  });

  testWidgets('pending shows a pending pill with the reason', (tester) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) => MockAccountRepository(
            latency: Duration.zero,
            kycStatus: VerificationStatus.pending,
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Pending'), findsOneWidget);
    expect(find.text('Your verification is being checked.'), findsOneWidget);
    expect(find.text('Verify identity'), findsNothing);
  });

  testWidgets('a load failure offers a retry', (tester) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) => _FailingAccountRepository(),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.text('We couldn’t load your account.'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('verified shows no verification action required', (tester) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) => MockAccountRepository(
            latency: Duration.zero,
            kycStatus: VerificationStatus.verified,
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Verified'), findsOneWidget);
    expect(find.text('Verify identity'), findsNothing);
  });

  testWidgets('suspended states the reason and disables payment methods', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) => MockAccountRepository(
            latency: Duration.zero,
            accountStatus: 'suspended',
            paymentMethodsList: const [
              PaymentMethod(id: 'pm_1', label: 'Sabi wallet', kind: 'wallet'),
            ],
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Suspended'), findsOneWidget);
    expect(find.textContaining('This account is suspended'), findsOneWidget);
    expect(find.text('Sabi wallet'), findsNothing);
    expect(find.text('Verify identity'), findsNothing);
  });

  testWidgets('changing the locale re-renders with a fallback note', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) => MockAccountRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.byType(DropdownButton<AppLocale>), findsOneWidget);
    containerOf(tester).read(localeProvider.notifier).set(AppLocale.pidgin);
    await tester.pumpAndSettle();
    expect(
      find.text('Some words still dey English while we finish this language.'),
      findsOneWidget,
    );
    expect(
      find.text('Verify your identity before you go pay.'),
      findsOneWidget,
    );
  });

  testWidgets('offline keeps the last known details and shows the banner', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) => MockAccountRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();
    expect(
      find.text('Showing your last known account details.'),
      findsOneWidget,
    );
    expect(find.text('Ngozi'), findsOneWidget);
  });
}
