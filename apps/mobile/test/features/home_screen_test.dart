import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/skeleton.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/home/home_controller.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/models/receipt_summary.dart';

import '../helpers.dart';

ReceiptSummary _receipt(String id, String payee, PaymentStatus status) =>
    ReceiptSummary(
      id: id,
      reference: 'REF-$id',
      payee: payee,
      amount: 150000,
      currency: 'NGN',
      kind: 'Biller',
      status: status,
      issuedAt: DateTime.utc(2026, 9, 20),
    );

List<Override> _overrides({
  Duration latency = Duration.zero,
  List<ReceiptSummary>? receipts,
  MockCatalogueRepository? catalogue,
}) => [
  receiptRepositoryProvider.overrideWith(
    (ref) => MockReceiptRepository(latency: latency, receipts: receipts),
  ),
  catalogueRepositoryProvider.overrideWith(
    (ref) => catalogue ?? MockCatalogueRepository(latency: Duration.zero),
  ),
];

void main() {
  testWidgets('first load shows the skeleton', (tester) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(
        latency: const Duration(milliseconds: 200),
        receipts: [_receipt('1', 'MTN Nigeria', PaymentStatus.settled)],
      ),
    );
    await tester.pump();
    expect(find.byType(SabSkeletonList), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.byType(SabSkeletonList), findsNothing);
  });

  testWidgets('no history shows the empty state', (tester) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    expect(find.text('No payments yet'), findsOneWidget);
  });

  testWidgets('loaded shows recent receipts with their status', (tester) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(
        receipts: [
          _receipt('1', 'Lagos State Government', PaymentStatus.settled),
          _receipt('2', 'MTN Nigeria', PaymentStatus.pending),
        ],
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Lagos State Government'), findsOneWidget);
    expect(find.text('MTN Nigeria'), findsOneWidget);
    expect(find.text('Settled'), findsOneWidget);
    expect(find.text('Pending'), findsOneWidget);
  });

  testWidgets('a request in flight disables the composer', (tester) async {
    final controller = MockCatalogueRepository(
      latency: const Duration(milliseconds: 200),
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const [], catalogue: controller),
    );
    await tester.pumpAndSettle();
    final future = containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('pay my land use charge');
    await tester.pump();
    expect(find.text('Working on it…'), findsOneWidget);
    final textField = tester.widget<TextField>(find.byType(TextField));
    expect(textField.enabled, isFalse);
    // Advance the fake clock so the pending resolution completes.
    await tester.pumpAndSettle();
    await future;
  });

  testWidgets('discovery results render as selectable service rows', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('pay my land use charge');
    await tester.pumpAndSettle();
    expect(find.text('Lagos State Government'), findsOneWidget);
    expect(find.text('Land Use Charge'), findsOneWidget);
  });

  testWidgets('low confidence asks one question with the closest candidates', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('I wan pay my electricity');
    await tester.pumpAndSettle();
    expect(find.text('Just to confirm'), findsOneWidget);
    expect(find.text('Which electricity provider do you pay?'), findsOneWidget);
    expect(find.text('Ikeja Electric'), findsOneWidget);
  });

  testWidgets(
    'a catalogue miss states the gap instead of inventing a service',
    (tester) async {
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(receipts: const []),
      );
      await tester.pumpAndSettle();
      containerOf(tester)
          .read(homeControllerProvider.notifier)
          .submit('pay my xyz subscription');
      await tester.pumpAndSettle();
      expect(find.text('Not covered yet'), findsOneWidget);
      expect(find.text('Contact support'), findsOneWidget);
    },
  );

  testWidgets(
    'a resolution failure offers a retry that preserves the request',
    (tester) async {
      final controller = MockCatalogueRepository(latency: Duration.zero)
        ..failNext = true;
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(receipts: const [], catalogue: controller),
      );
      await tester.pumpAndSettle();
      containerOf(tester)
          .read(homeControllerProvider.notifier)
          .submit('pay my land use charge');
      await tester.pumpAndSettle();
      expect(
        find.text(
          'We couldn’t work that out. Check your connection and try again.',
        ),
        findsOneWidget,
      );
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      // The retry resolves the preserved request.
      expect(find.text('Lagos State Government'), findsOneWidget);
    },
  );

  testWidgets('offline queues the request and blocks authorisation', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();
    expect(
      find.text('Payments can’t be authorised while you’re offline.'),
      findsOneWidget,
    );
    containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('pay my land use charge');
    await tester.pumpAndSettle();
    expect(
      find.text(
        'Your request is queued and will send when you’re back online.',
      ),
      findsOneWidget,
    );
  });
}
