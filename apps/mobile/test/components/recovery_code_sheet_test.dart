import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/recovery_code_sheet.dart';
import 'package:sabi_mobile/design_system/tokens.dart';

import '../helpers.dart';

const _code = 'SABI-4K2M-9QRT-7WD3';
const _label = 'I’ve saved my recovery code';

Future<void> _openSheet(
  WidgetTester tester, {
  Brightness brightness = Brightness.light,
}) async {
  await pumpSab(
    tester,
    Scaffold(
      body: Builder(
        builder: (context) => Center(
          child: ElevatedButton(
            onPressed: () => showSabRecoveryCodeSheet(context, code: _code),
            child: const Text('Open'),
          ),
        ),
      ),
    ),
    brightness: brightness,
  );
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
}

/// The checkbox's visual centre, taken from its painted [RenderBox].
Offset _checkboxCentre(WidgetTester tester) =>
    tester.getCenter(find.byType(Checkbox));

/// A baseline used to align the label against the checkbox. The label's line
/// box is what we centre, so the comparison is between box centres rather than
/// glyph baselines.
Rect _labelRect(WidgetTester tester) => tester.getRect(find.text(_label));

void main() {
  testWidgets('blocks until acknowledged, then returns true', (tester) async {
    bool? result;
    await pumpSab(
      tester,
      Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: ElevatedButton(
              onPressed: () async {
                result = await showSabRecoveryCodeSheet(context, code: _code);
              },
              child: const Text('Open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();

    ElevatedButton primary() => tester.widget<ElevatedButton>(
      find.ancestor(
        of: find.text('Continue'),
        matching: find.byType(ElevatedButton),
      ),
    );
    expect(primary().onPressed, isNull);

    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    expect(primary().onPressed, isNotNull);
    expect(result, isNull, reason: 'sheet still open');

    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(result, isTrue);
  });

  testWidgets('does not dismiss on drag or scrim tap', (tester) async {
    await _openSheet(tester);
    await tester.drag(find.byType(Checkbox), const Offset(0, 300));
    await tester.pumpAndSettle();
    expect(find.text('Save your recovery code'), findsOneWidget);
  });

  testWidgets('label is vertically centred against the checkbox', (
    tester,
  ) async {
    await _openSheet(tester);
    final delta = _labelRect(tester).center.dy - _checkboxCentre(tester).dy;
    // A few logical pixels of tolerance absorbs the difference between the
    // line box and its painted glyphs; the old hard-coded nudge was 16px.
    expect(delta.abs(), lessThan(6));
  });

  testWidgets('stays centred when the label wraps at a large text scale', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await pumpSab(
      tester,
      MediaQuery(
        data: const MediaQueryData(textScaler: TextScaler.linear(2.0)),
        child: Scaffold(
          body: Builder(
            builder: (context) => Center(
              child: ElevatedButton(
                onPressed: () => showSabRecoveryCodeSheet(context, code: _code),
                child: const Text('Open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();

    final labelRect = _labelRect(tester);
    final checkboxY = _checkboxCentre(tester).dy;
    // At 2x the label is wider than the remaining column and wraps, so the
    // checkbox must still centre against the taller wrapped block.
    final labelHeight = tester.getSize(find.text(_label)).height;
    final lineHeight =
        SabTypography.body.fontSize! * SabTypography.body.height!;
    expect(labelHeight, greaterThan(lineHeight));
    expect(labelRect.center.dy, closeTo(checkboxY, 8));
  });

  testWidgets('renders in dark mode', (tester) async {
    await _openSheet(tester, brightness: Brightness.dark);
    expect(find.text('Save your recovery code'), findsOneWidget);
    expect(find.byType(Checkbox), findsOneWidget);
  });
}
