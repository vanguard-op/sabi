import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/status_pill.dart';
import 'package:sabi_mobile/design_system/icons.dart';

import '../helpers.dart';

void main() {
  final cases = <SabStatus, (String label, IconData icon)>{
    SabStatus.pending: ('Pending', SabIcons.statusPending),
    SabStatus.settled: ('Settled', SabIcons.statusSettled),
    SabStatus.failed: ('Failed', SabIcons.statusFailed),
    SabStatus.awaitingReceipt: (
      'Awaiting receipt',
      SabIcons.statusAwaitingReceipt,
    ),
    SabStatus.unverified: ('Not verified', SabIcons.statusUnverified),
    SabStatus.verified: ('Verified', SabIcons.statusVerified),
    SabStatus.suspended: ('Suspended', SabIcons.statusSuspended),
  };

  for (final MapEntry(key: status, value: expected) in cases.entries) {
    testWidgets('$status carries both an icon and a text label', (
      tester,
    ) async {
      await pumpSab(tester, Scaffold(body: StatusPill(status: status)));
      expect(find.text(expected.$1), findsOneWidget);
      expect(find.byIcon(expected.$2), findsOneWidget);
    });
  }

  testWidgets('label override wins over the default copy', (tester) async {
    await pumpSab(
      tester,
      const Scaffold(
        body: StatusPill(status: SabStatus.verified, label: 'Linked'),
      ),
    );
    expect(find.text('Linked'), findsOneWidget);
    expect(find.text('Verified'), findsNothing);
  });

  testWidgets('renders on the dark token set', (tester) async {
    await pumpSab(
      tester,
      const Scaffold(body: StatusPill(status: SabStatus.failed)),
      brightness: Brightness.dark,
    );
    expect(find.text('Failed'), findsOneWidget);
    expect(find.byIcon(SabIcons.statusFailed), findsOneWidget);
  });
}
