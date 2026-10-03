import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/sab_button.dart';
import 'package:sabi_mobile/design_system/theme.dart';
import 'package:sabi_mobile/design_system/tokens.dart';

/// A disabled control must not paint its enabled fill: a button that looks
/// tappable when it is not is a real defect (branding.md, "Component Tokens";
/// the Accessibility disabled treatment).
void main() {
  Future<ButtonStyle> styleFor(
    WidgetTester tester, {
    required SabButtonVariant variant,
    required bool enabled,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildSabTheme(Brightness.light),
        home: Scaffold(
          body: SabButton(
            label: 'Continue',
            variant: variant,
            onPressed: enabled ? () {} : null,
          ),
        ),
      ),
    );
    final button = tester.widget<ButtonStyleButton>(
      find.byWidgetPredicate((w) => w is ButtonStyleButton),
    );
    return button.style!;
  }

  Color? fill(ButtonStyle style, Set<WidgetState> states, WidgetState state) =>
      style.backgroundColor?.resolve(states);

  testWidgets('a disabled primary button fades its fill', (tester) async {
    final enabled = await styleFor(
      tester,
      variant: SabButtonVariant.primary,
      enabled: true,
    );
    final disabled = await styleFor(
      tester,
      variant: SabButtonVariant.primary,
      enabled: false,
    );

    final enabledFill = fill(enabled, {}, WidgetState.disabled)!;
    final disabledFill = fill(disabled, {
      WidgetState.disabled,
    }, WidgetState.disabled)!;

    expect(disabledFill, isNot(equals(enabledFill)));
    expect(disabledFill.a, closeTo(SabSizes.disabledOpacity, 0.01));
  });

  testWidgets(
    'a disabled destructive button does not show the full error fill',
    (tester) async {
      final style = await styleFor(
        tester,
        variant: SabButtonVariant.destructive,
        enabled: false,
      );
      final resolved = fill(style, {
        WidgetState.disabled,
      }, WidgetState.disabled)!;
      expect(resolved.a, closeTo(SabSizes.disabledOpacity, 0.01));
    },
  );

  testWidgets('an enabled button is unaffected by the disabled rule', (
    tester,
  ) async {
    final style = await styleFor(
      tester,
      variant: SabButtonVariant.primary,
      enabled: true,
    );
    final resolved = fill(style, {}, WidgetState.disabled)!;
    expect(resolved.a, closeTo(1.0, 0.01));
  });
}
