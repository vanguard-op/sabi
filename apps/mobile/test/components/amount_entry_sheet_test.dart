import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/amount_entry_sheet.dart';

import '../helpers.dart';

Future<void> _openSheet(WidgetTester tester) async {
  await pumpSab(
    tester,
    Scaffold(
      body: Builder(
        builder: (context) => Center(
          child: ElevatedButton(
            onPressed: () => showSabAmountEntrySheet(
              context,
              minMinor: 10000,
              maxMinor: 500000,
            ),
            child: const Text('Open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('rejects an amount below the provider range', (tester) async {
    await _openSheet(tester);
    await tester.enterText(find.byType(TextField), '50');
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(
      find.text('Enter an amount within the allowed range.'),
      findsOneWidget,
    );
  });

  testWidgets('rejects an amount above the provider range', (tester) async {
    await _openSheet(tester);
    await tester.enterText(find.byType(TextField), '9000');
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(
      find.text('Enter an amount within the allowed range.'),
      findsOneWidget,
    );
  });

  testWidgets('rejects an empty amount', (tester) async {
    await _openSheet(tester);
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('This is needed'), findsOneWidget);
  });

  testWidgets('returns a valid amount in minor units', (tester) async {
    int? result;
    await pumpSab(
      tester,
      Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: ElevatedButton(
              onPressed: () async {
                result = await showSabAmountEntrySheet(
                  context,
                  minMinor: 10000,
                  maxMinor: 500000,
                );
              },
              child: const Text('Open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '1500');
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(result, 150000);
  });
}
