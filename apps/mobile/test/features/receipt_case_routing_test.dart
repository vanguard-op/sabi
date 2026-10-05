import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/features.dart';
import 'package:sabi_mobile/core/session.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/case/case_screen.dart';
import 'package:sabi_mobile/features/receipts/receipt_detail_screen.dart';
import 'package:sabi_mobile/models/receipt.dart';
import 'package:sabi_mobile/router/app_router.dart';

import '../helpers.dart';

/// The feature set with the receipt and case surfaces on, so their routes
/// render the real screens rather than the gated fallback.
const _enabled = SabFeatureFlags({
  SabFeature.passwordlessOnboarding,
  SabFeature.receiptCapture,
  SabFeature.failureRecovery,
});

List<Override> _overrides(
  SabFeatureFlags flags, {
  ReceiptsRepository? receipts,
}) => [
  authRepositoryProvider.overrideWith(
    (ref) => MockAuthRepository(latency: Duration.zero),
  ),
  accountRepositoryProvider.overrideWith(
    (ref) => MockAccountRepository(latency: Duration.zero),
  ),
  receiptRepositoryProvider.overrideWith(
    (ref) => MockReceiptRepository(latency: Duration.zero),
  ),
  receiptsRepositoryProvider.overrideWith(
    (ref) => receipts ?? MockReceiptsRepository(latency: Duration.zero),
  ),
  casesRepositoryProvider.overrideWith(
    (ref) => MockCasesRepository(latency: Duration.zero),
  ),
  featureFlagsProvider.overrideWithValue(flags),
  sessionProvider.overrideWith((ref) {
    final store = SessionStore()..signIn();
    ref.onDispose(store.dispose);
    return store;
  }),
];

void main() {
  testWidgets('an enabled receipt deep link renders Receipt Detail', (
    tester,
  ) async {
    await pumpSabApp(tester, overrides: _overrides(_enabled));
    await tester.pumpAndSettle();
    containerOf(tester).read(routerProvider).go('/receipts/rcp_1');
    await tester.pumpAndSettle();
    expect(find.byType(ReceiptDetailScreen), findsOneWidget);
    // The gate must not stack a second AppBar above the screen's own.
    expect(find.byType(AppBar), findsOneWidget);
  });

  testWidgets('an enabled case deep link renders Case', (tester) async {
    await pumpSabApp(tester, overrides: _overrides(_enabled));
    await tester.pumpAndSettle();
    containerOf(tester).read(routerProvider).go('/cases/case_1');
    await tester.pumpAndSettle();
    expect(find.byType(CaseScreen), findsOneWidget);
    expect(find.byType(AppBar), findsOneWidget);
  });

  testWidgets('the Receipt Detail dispute action opens the Case screen', (
    tester,
  ) async {
    // The receipt's payment matches case_1's payment, so Receipt Detail resolves
    // the case and opens it (screen 8, Entry Points: Receipt Detail).
    final detail = ReceiptDetail(
      receipt: Receipt(
        id: 'rcp_case',
        paymentId: 'pay_failed_1',
        kind: ReceiptKind.officialEReceipt,
        verificationStatus: ReceiptVerification.verified,
        documentRef: 'docs/rcp_case.pdf',
        issuedAt: DateTime.utc(2026, 9, 28, 10, 30),
        createdAt: DateTime.utc(2026, 9, 28, 10, 31),
      ),
      payment: ReceiptPayment(
        paymentId: 'pay_failed_1',
        serviceId: 'svc_1',
        amount: 500000,
        currency: 'NGN',
        payee: 'Ikeja Electric',
        status: 'failed',
        channel: 'app',
        createdAt: DateTime.utc(2026, 9, 28, 10, 30),
        updatedAt: DateTime.utc(2026, 9, 28, 10, 31),
      ),
    );
    await pumpSabApp(
      tester,
      overrides: _overrides(
        _enabled,
        receipts: MockReceiptsRepository(
          latency: Duration.zero,
          details: [detail],
        ),
      ),
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(routerProvider).go('/receipts/rcp_case');
    await tester.pumpAndSettle();

    final dispute = find.text('Raise a dispute');
    await tester.ensureVisible(dispute);
    await tester.pumpAndSettle();
    await tester.tap(dispute);
    await tester.pumpAndSettle();

    expect(find.byType(CaseScreen), findsOneWidget);
  });

  testWidgets('a receipt deep link without the feature shows the fallback', (
    tester,
  ) async {
    await pumpSabApp(tester, overrides: _overrides(SabFeatureFlags.phase1));
    await tester.pumpAndSettle();
    containerOf(tester).read(routerProvider).go('/receipts/rcp_1');
    await tester.pumpAndSettle();
    expect(find.byType(ReceiptDetailScreen), findsNothing);
    expect(find.text('Coming soon'), findsOneWidget);
  });
}
