import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/receipt_card.dart';
import 'package:sabi_mobile/models/receipt_summary.dart';

import '../helpers.dart';

void main() {
  ReceiptSummary receipt({
    String payee = 'Lagos State Government',
    String reference = 'LUC-2026-0001',
    int amount = 2500000,
    PaymentStatus status = PaymentStatus.settled,
  }) => ReceiptSummary(
    id: 'rcp_1',
    reference: reference,
    payee: payee,
    amount: amount,
    currency: 'NGN',
    issuedAt: DateTime.utc(2026, 9, 28, 10, 30),
    kind: 'Government',
    status: status,
  );

  // Mirrors real usage: cards live in a ListView, so the card's own height is
  // unconstrained and only the horizontal axis can overflow.
  Widget host(ReceiptSummary item, {VoidCallback? onTap}) => Scaffold(
    body: ListView(
      padding: const EdgeInsets.all(16),
      children: [ReceiptCard(receipt: item, onTap: onTap)],
    ),
  );

  testWidgets('shows the formatted amount and the status pill', (tester) async {
    await pumpSab(tester, host(receipt(status: PaymentStatus.awaitingReceipt)));
    expect(find.text('₦25,000.00'), findsOneWidget);
    expect(find.text('Awaiting receipt'), findsOneWidget);
  });

  testWidgets('opens Receipt Detail when tapped', (tester) async {
    var opened = 0;
    await pumpSab(tester, host(receipt(), onTap: () => opened++));
    await tester.tap(find.byType(ReceiptCard));
    expect(opened, 1);
  });

  // A narrow phone with a long payee, a long amount, and the longest status
  // label must not overflow (screens.md, "Receipt Card";
  // docs/Sabi/screens/06-receipts.md states). 320dp is below the common phone.
  testWidgets('lays out without overflow on a narrow phone', (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await pumpSab(
      tester,
      host(
        receipt(
          payee: 'Lagos State Government Land Use Charge Directorate',
          reference: 'LUC-2026-0001-VERY-LONG-REFERENCE',
          amount: 123456789,
          status: PaymentStatus.awaitingReceipt,
        ),
        onTap: () {},
      ),
    );
    await tester.pumpAndSettle();
  });

  testWidgets('renders on the dark token set', (tester) async {
    await pumpSab(
      tester,
      host(receipt(status: PaymentStatus.failed)),
      brightness: Brightness.dark,
    );
    expect(find.text('₦25,000.00'), findsOneWidget);
    expect(find.text('Failed'), findsOneWidget);
  });
}
