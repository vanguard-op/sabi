import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/skeleton.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/account/account_screen.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/account.dart';
import 'package:sabi_mobile/models/channel_link.dart';
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
    // The profile group states the account status next to the display name.
    expect(find.text('Account status'), findsOneWidget);
    expect(find.text('Active'), findsOneWidget);
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
    // The profile row and the verification pill both state the suspended state.
    expect(find.text('Suspended'), findsNWidgets(2));
    expect(find.textContaining('This account is suspended'), findsOneWidget);
    expect(find.text('Sabi wallet'), findsNothing);
    expect(find.text('Verify identity'), findsNothing);
    // The profile group carries the same suspended status, not "Active".
    expect(find.text('Account status'), findsOneWidget);
    expect(find.text('Active'), findsNothing);
  });

  testWidgets('a channel link without a verification stamp reads as pending', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) => MockAccountRepository(
            latency: Duration.zero,
            channelLinks: const [
              ChannelLink(
                id: 'link_1',
                channel: 'whatsapp',
                address: '08030000000',
              ),
            ],
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('08030000000'), findsOneWidget);
    expect(find.text('Pending'), findsOneWidget);
    // The unlinked channels still offer the link action.
    expect(find.text('Link'), findsNWidgets(2));
  });

  testWidgets('a verified channel link is labelled as linked', (tester) async {
    await pumpSab(
      tester,
      const AccountScreen(),
      overrides: [
        accountRepositoryProvider.overrideWith(
          (ref) => MockAccountRepository(
            latency: Duration.zero,
            channelLinks: [
              ChannelLink(
                id: 'link_1',
                channel: 'whatsapp',
                address: '08030000000',
                verifiedAt: DateTime.utc(2026, 10, 1),
              ),
            ],
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Linked'), findsOneWidget);
    expect(find.text('Pending'), findsNothing);
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
