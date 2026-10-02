import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:sabi_mobile/core/features.dart';
import 'package:sabi_mobile/core/money.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';

void main() {
  setUpAll(() async {
    await initializeDateFormatting('en_NG');
  });

  group('money', () {
    test('formats minor units to naira at the edge', () {
      expect(SabMoney.format(2500000), contains('25,000.00'));
      expect(SabMoney.format(2500000), startsWith('₦'));
    });

    test('a non-NGN currency keeps its code', () {
      expect(SabMoney.format(1000, currency: 'USD'), contains('USD'));
    });

    test('dates are formatted through the locale, not a hardcoded pattern', () {
      expect(SabMoney.formatDate(DateTime.utc(2026, 9, 28)), contains('2026'));
    });
  });

  group('locale strings', () {
    test('switching to pidgin falls back per key and flags the fallback', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      expect(container.read(sabStringsProvider).signOut, 'Sign out');
      expect(container.read(sabStringsProvider).hasFallback, isFalse);
      container.read(localeProvider.notifier).set(AppLocale.pidgin);
      expect(container.read(sabStringsProvider).signOut, 'Comot');
      expect(container.read(sabStringsProvider).hasFallback, isTrue);
    });
  });

  group('feature gates', () {
    test('Phase 1 enables discovery and composed surfaces', () {
      expect(
        SabFeatureFlags.phase1.isEnabled(SabFeature.passwordlessOnboarding),
        isTrue,
      );
      expect(
        SabFeatureFlags.phase1.isEnabled(SabFeature.serviceDiscovery),
        isTrue,
      );
      expect(
        SabFeatureFlags.phase1.isEnabled(SabFeature.composedSurfaces),
        isTrue,
      );
    });

    test('later-phase payment surfaces stay gated', () {
      expect(
        SabFeatureFlags.phase1.isEnabled(SabFeature.paymentAuthorization),
        isFalse,
      );
      expect(
        SabFeatureFlags.phase1.isEnabled(SabFeature.identityVerification),
        isFalse,
      );
    });

    test('every feature carries its durable id and phase', () {
      expect(SabFeature.passwordlessOnboarding.featId, 'FEAT-001');
      expect(SabFeature.serviceDiscovery.featId, 'FEAT-004');
      expect(SabFeature.composedSurfaces.featId, 'FEAT-011');
      expect(SabFeature.paymentAuthorization.phase, 2);
    });
  });
}
