import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/skeleton.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/receipts/receipt_detail_screen.dart';
import 'package:sabi_mobile/models/receipt.dart';

import '../helpers.dart';

ReceiptDetail _detail({
  required ReceiptVerification verification,
  String? receiptNumber,
  String? unverifiedReason,
  ReceiptKind kind = ReceiptKind.officialEReceipt,
}) => ReceiptDetail(
  receipt: Receipt(
    id: 'rcp_1',
    paymentId: 'pay_1',
    kind: kind,
    receiptNumber: receiptNumber,
    verificationStatus: verification,
    unverifiedReason: unverifiedReason,
    documentRef: 'docs/rcp_1.pdf',
    issuedAt: DateTime.utc(2026, 9, 28, 10, 30),
    createdAt: DateTime.utc(2026, 9, 28, 10, 31),
  ),
  payment: ReceiptPayment(
    paymentId: 'pay_1',
    serviceId: 'svc_1',
    amount: 2500000,
    currency: 'NGN',
    payee: 'Lagos State Government',
    status: 'succeeded',
    channel: 'app',
    createdAt: DateTime.utc(2026, 9, 28, 10, 30),
    updatedAt: DateTime.utc(2026, 9, 28, 10, 31),
  ),
);

void main() {
  testWidgets('a verified receipt shows its official identifier and the '
      'verified line', (tester) async {
    await pumpSab(
      tester,
      const ReceiptDetailScreen(receiptId: 'rcp_1'),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(
            latency: Duration.zero,
            details: [
              _detail(
                verification: ReceiptVerification.verified,
                receiptNumber: 'FTeR-2026-000123',
              ),
            ],
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('FTeR-2026-000123'), findsOneWidget);
    expect(find.textContaining('confirmed against the source'), findsOneWidget);
    expect(find.text('Verified'), findsOneWidget);
  });

  testWidgets('an unverified receipt states the plain reason', (tester) async {
    await pumpSab(
      tester,
      const ReceiptDetailScreen(receiptId: 'rcp_1'),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(
            latency: Duration.zero,
            details: [
              _detail(
                verification: ReceiptVerification.unverified,
                receiptNumber: 'FTeR-2026-000999',
                unverifiedReason: 'The source could not find this identifier.',
              ),
            ],
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('The source could not find this identifier.'),
        findsOneWidget);
    expect(find.text('Not verified'), findsOneWidget);
  });

  testWidgets('an awaiting receipt shows the awaiting line and no identifier',
      (tester) async {
    await pumpSab(
      tester,
      const ReceiptDetailScreen(receiptId: 'rcp_1'),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(
            latency: Duration.zero,
            details: [_detail(verification: ReceiptVerification.pending)],
          ),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('still checking'), findsOneWidget);
    expect(find.text('Awaiting receipt'), findsOneWidget);
  });

  testWidgets('a missing receipt shows an error with a retry', (tester) async {
    await pumpSab(
      tester,
      const ReceiptDetailScreen(receiptId: 'missing'),
      overrides: [
        receiptsRepositoryProvider.overrideWith(
          (ref) => MockReceiptsRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('This receipt couldn’t be found.'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('the first load shows a skeleton', (tester) async {
    await pumpSab(
      tester,
      const ReceiptDetailScreen(receiptId: 'rcp_1'),
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
    expect(find.text('Lagos State Government'), findsOneWidget);
  });
}
