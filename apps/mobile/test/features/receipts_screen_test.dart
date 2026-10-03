import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/skeleton.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/receipts/receipts_screen.dart';
import 'package:sabi_mobile/models/receipt.dart';

import '../helpers.dart';

/// A receipts repository that fails the first list call (FEAT-008 error state).
class _FailingReceiptsRepository extends MockReceiptsRepository {
  _FailingReceiptsRepository() : super(latency: Duration.zero);

  @override
  Future<ReceiptPage> list({String? query, String? cursor, int limit = 20}) =>
      throw Exception('transport down');
}

ReceiptDetail _detail({
  required String id,
  required String payee,
  required String reference,
  int amount = 2500000,
  ReceiptVerification verification = ReceiptVerification.verified,
  DateTime? issuedAt,
}) => ReceiptDetail(
  receipt: Receipt(
    id: id,
    paymentId: 'pay_$id',
    kind: ReceiptKind.officialEReceipt,
    receiptNumber: 'FTeR-$id',
    verificationStatus: verification,
    documentRef: 'docs/$id.pdf',
    issuedAt: issuedAt ?? DateTime.utc(2026, 9, 28, 10, 30),
    createdAt: issuedAt ?? DateTime.utc(2026, 9, 28, 10, 30),
  ),
  payment: ReceiptPayment(
    paymentId: 'pay_$id',
    serviceId: 'svc_1',
    amount: amount,
    currency: 'NGN',
    payee: payee,
    status: 'succeeded',
    channel: 'app',
    createdAt: issuedAt ?? DateTime.utc(2026, 9, 28, 10, 30),
    updatedAt: issuedAt ?? DateTime.utc(2026, 9, 28, 10, 30),
  ),
);

void main() {
  testWidgets('first load shows the skeleton', (tester) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(
            latency: const Duration(milliseconds: 200),
          ),
        ),
      ],
    );
    await tester.pump();
    expect(find.byType(SabSkeletonList), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.byType(SabSkeletonList), findsNothing);
  });

  testWidgets('an empty history shows the empty state with a first-payment '
      'prompt', (tester) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(latency: Duration.zero, details: []),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('No receipts yet'), findsOneWidget);
    expect(find.text('Make a payment'), findsOneWidget);
  });

  testWidgets('loaded receipts group under a month heading', (tester) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Lagos State Government'), findsWidgets);
    expect(find.text('MTN Nigeria'), findsOneWidget);
    // The seed spans September, August, and July; each month gets a heading.
    expect(find.text('September 2026'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('July 2026'),
      200,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('July 2026'), findsOneWidget);
  });

  testWidgets('searching by agency returns only the match', (tester) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'MTN');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.text('MTN Nigeria'), findsOneWidget);
    expect(find.text('Lagos State Government'), findsNothing);
  });

  testWidgets('a search with no matches names the query and clears', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'nothing-matches');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.text('No matches'), findsOneWidget);
    expect(find.textContaining('nothing-matches'), findsWidgets);
    await tester.tap(find.text('Clear search'));
    await tester.pumpAndSettle();
    expect(find.text('Lagos State Government'), findsWidgets);
  });

  testWidgets('a load failure offers a retry', (tester) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => _FailingReceiptsRepository(),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('offline keeps the saved receipts and shows the banner', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();
    expect(find.textContaining('Showing your saved receipts'), findsOneWidget);
    expect(find.text('Lagos State Government'), findsWidgets);
  });

  testWidgets('an awaiting receipt shows the awaiting pill, not a hidden row', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(
            latency: Duration.zero,
            details: [
              _detail(
                id: 'rcp_pending',
                payee: 'MTN Nigeria',
                reference: 'MTN-1',
                verification: ReceiptVerification.pending,
              ),
            ],
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('MTN Nigeria'), findsOneWidget);
    expect(find.text('Awaiting receipt'), findsOneWidget);
  });
}
