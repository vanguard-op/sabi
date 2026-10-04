import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/design_system/theme.dart';
import 'package:sabi_mobile/design_system/tokens.dart';

/// Guards the system status and navigation bars against both Flutter's default
/// black navigation bar, Material's default per-screen colour, and a
/// transparent bar that lets Android's device-themed window background show
/// through: the bars carry the theme surface with icons that contrast it, in
/// both modes (NFR-030; D-037).
void main() {
  final light = SabColorTokens.light;
  final dark = SabColorTokens.dark;

  group('token system bar style', () {
    test('light mode paints the light surface with dark icons', () {
      final style = sabSystemOverlayStyle(light);
      expect(style.statusBarColor, light.surface);
      expect(style.systemNavigationBarColor, light.surface);
      expect(style.systemNavigationBarDividerColor, light.surface);
      expect(style.statusBarIconBrightness, Brightness.dark);
      expect(style.systemNavigationBarIconBrightness, Brightness.dark);
      // iOS reads the background brightness, which is the inverse of its icons.
      expect(style.statusBarBrightness, Brightness.light);
    });

    test('dark mode paints the dark surface with light icons', () {
      final style = sabSystemOverlayStyle(dark);
      expect(style.statusBarColor, dark.surface);
      expect(style.systemNavigationBarColor, dark.surface);
      expect(style.systemNavigationBarDividerColor, dark.surface);
      expect(style.statusBarIconBrightness, Brightness.light);
      expect(style.systemNavigationBarIconBrightness, Brightness.light);
      expect(style.statusBarBrightness, Brightness.dark);
    });

    test('bars are opaque so the device window cannot show through', () {
      // A transparent bar let Android paint its own device-themed window
      // background behind it below API 35 (D-037).
      for (final colors in [light, dark]) {
        final style = sabSystemOverlayStyle(colors);
        expect(style.statusBarColor, isNot(Colors.transparent));
        expect(style.systemNavigationBarColor, isNot(Colors.transparent));
        expect(
          style.systemNavigationBarDividerColor,
          isNot(Colors.transparent),
        );
      }
    });

    test('never falls back to the default black bar', () {
      for (final colors in [light, dark]) {
        final style = sabSystemOverlayStyle(colors);
        expect(style.systemNavigationBarColor, isNot(const Color(0xFF000000)));
        expect(style.statusBarColor, isNot(const Color(0xFF000000)));
      }
    });

    test('contrast scrims are disabled so the surface colour is not toned', () {
      for (final colors in [light, dark]) {
        final style = sabSystemOverlayStyle(colors);
        expect(style.systemStatusBarContrastEnforced, isFalse);
        expect(style.systemNavigationBarContrastEnforced, isFalse);
      }
    });
  });

  group('theme wiring', () {
    test('the app bar theme carries the token overlay style per mode', () {
      expect(
        buildSabTheme(Brightness.light).appBarTheme.systemOverlayStyle,
        sabSystemOverlayStyle(light),
      );
      expect(
        buildSabTheme(Brightness.dark).appBarTheme.systemOverlayStyle,
        sabSystemOverlayStyle(dark),
      );
    });

    test('the scaffold surface is the token surface behind the bars', () {
      // On API 35+ the bar colour is ignored under enforced edge-to-edge, so
      // the scaffold background is what shows behind the bar (D-037).
      expect(
        buildSabTheme(Brightness.light).scaffoldBackgroundColor,
        light.surface,
      );
      expect(
        buildSabTheme(Brightness.dark).scaffoldBackgroundColor,
        dark.surface,
      );
    });
  });

  group('surfaces without an app bar', () {
    Future<SystemUiOverlayStyle?> pumpAndRead(
      WidgetTester tester, {
      required Brightness brightness,
      required Widget child,
    }) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: buildSabTheme(brightness),
          home: SabSystemBars(child: child),
        ),
      );
      final region = tester.widget<AnnotatedRegion<SystemUiOverlayStyle>>(
        find
            .ancestor(
              of: find.byType(Scaffold),
              matching: find.byType(AnnotatedRegion<SystemUiOverlayStyle>),
            )
            .first,
      );
      return region.value;
    }

    testWidgets('a scaffold without an app bar gets the token style', (
      tester,
    ) async {
      final style = await pumpAndRead(
        tester,
        brightness: Brightness.light,
        child: const Scaffold(body: SizedBox.shrink()),
      );
      expect(style, sabSystemOverlayStyle(light));
    });

    testWidgets('the dark surface flips the icons', (tester) async {
      final style = await pumpAndRead(
        tester,
        brightness: Brightness.dark,
        child: const Scaffold(body: SizedBox.shrink()),
      );
      expect(style?.systemNavigationBarIconBrightness, Brightness.light);
      expect(style, sabSystemOverlayStyle(dark));
    });
  });
}
