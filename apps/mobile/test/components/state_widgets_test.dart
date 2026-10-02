import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/empty_state.dart';
import 'package:sabi_mobile/components/error_state.dart';
import 'package:sabi_mobile/components/offline_banner.dart';
import 'package:sabi_mobile/components/skeleton.dart';

import '../helpers.dart';

void main() {
  testWidgets('empty state shows illustration, copy, and one action', (
    tester,
  ) async {
    var tapped = false;
    await pumpSab(
      tester,
      Scaffold(
        body: EmptyState(
          title: 'No payments yet',
          message: 'Tell Sabi what you need to pay.',
          actionLabel: 'Get started',
          onAction: () => tapped = true,
        ),
      ),
    );
    expect(find.text('No payments yet'), findsOneWidget);
    expect(find.text('Tell Sabi what you need to pay.'), findsOneWidget);
    await tester.tap(find.text('Get started'));
    expect(tapped, isTrue);
  });

  testWidgets('error state retries through its primary action', (tester) async {
    var retried = 0;
    await pumpSab(
      tester,
      Scaffold(
        body: ErrorState(
          message: 'We could not load your activity.',
          retryLabel: 'Try again',
          onRetry: () => retried++,
        ),
      ),
    );
    expect(find.text('Something went wrong'), findsOneWidget);
    await tester.tap(find.text('Try again'));
    expect(retried, 1);
  });

  testWidgets('offline banner announces the queued state as a live region', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await pumpSab(
      tester,
      const Scaffold(
        body: OfflineBanner(
          message: 'You are offline.',
          queuedLabel: '1 request queued',
        ),
      ),
    );
    expect(find.text('You are offline.'), findsOneWidget);
    expect(find.text('1 request queued'), findsOneWidget);
    final semantics = tester.getSemantics(find.byType(OfflineBanner));
    expect(semantics.flagsCollection.isLiveRegion, isTrue);
    handle.dispose();
  });

  testWidgets('skeleton list renders its receipt-shaped placeholders', (
    tester,
  ) async {
    await pumpSab(tester, const Scaffold(body: SabSkeletonList(rows: 3)));
    expect(find.byType(SabSkeleton), findsWidgets);
  });
}
