import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/skeleton.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/receipts/receipts_screen.dart';
import 'package:sabi_mobile/models/receipt_summary.dart';

import '../helpers.dart';

class _FailingReceiptRepository extends MockReceiptRepository {
  _FailingReceiptRepository() : super(latency: Duration.zero);

  @override
  Future<List<ReceiptSummary>> recent({int limit = 10}) async =>
      throw Exception('transport down');
}

void main() {
  testWidgets('first load shows the skeleton', (tester) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptRepositoryProvider.overrideWith(
          (ref) =>
              MockReceiptRepository(latency: const Duration(milliseconds: 200)),
        ),
      ],
    );
    await tester.pump();
    expect(find.byType(SabSkeletonList), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.byType(SabSkeletonList), findsNothing);
  });

  testWidgets('an empty list shows the empty state and hides the shell', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptRepositoryProvider.overrideWith(
          (ref) =>
              MockReceiptRepository(latency: Duration.zero, receipts: const []),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('No receipts yet'), findsOneWidget);
  });

  testWidgets('loaded receipts render as cards', (tester) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptRepositoryProvider.overrideWith(
          (ref) => MockReceiptRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    expect(find.text('Lagos State Government'), findsOneWidget);
    expect(find.text('MTN Nigeria'), findsOneWidget);
    expect(find.text('Settled'), findsOneWidget);
  });

  testWidgets('a load failure offers a retry', (tester) async {
    await pumpSab(
      tester,
      const ReceiptsScreen(),
      overrides: [
        receiptRepositoryProvider.overrideWith(
          (ref) => _FailingReceiptRepository(),
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
        receiptRepositoryProvider.overrideWith(
          (ref) => MockReceiptRepository(latency: Duration.zero),
        ),
      ],
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();
    expect(find.textContaining('Showing your saved receipts'), findsOneWidget);
    expect(find.text('Lagos State Government'), findsOneWidget);
  });
}
