import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/design_system/tokens.dart';

double _contrast(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  final hi = la > lb ? la : lb;
  final lo = la > lb ? lb : la;
  return (hi + 0.05) / (lo + 0.05);
}

void main() {
  final light = SabColorTokens.light;
  final dark = SabColorTokens.dark;

  group('documented colour anchors', () {
    test('primary anchors resolve to the branding values', () {
      expect(light.primary100, const Color(0xFFE3F2EC));
      expect(light.primary300, const Color(0xFF8FCDB2));
      expect(light.primary500, const Color(0xFF12805C));
      expect(light.primary700, const Color(0xFF0E5940));
      expect(light.primary900, const Color(0xFF0A3829));
    });

    test('primary scale fills all nine steps in order', () {
      final ramp = [
        light.primary100,
        light.primary200,
        light.primary300,
        light.primary400,
        light.primary500,
        light.primary600,
        light.primary700,
        light.primary800,
        light.primary900,
      ];
      expect(ramp.toSet(), hasLength(9));
      for (var i = 1; i < ramp.length; i++) {
        expect(
          ramp[i].computeLuminance(),
          lessThan(ramp[i - 1].computeLuminance()),
          reason: 'primary $i should be darker than its predecessor',
        );
      }
    });

    test('grey anchors and semantic roles are wired to the right shade', () {
      expect(light.grey50, const Color(0xFFFAF8F4));
      expect(light.grey100, const Color(0xFFEEEFE8));
      expect(light.grey300, const Color(0xFFC6C9BE));
      expect(light.grey600, const Color(0xFF5B5F54));
      expect(light.grey900, const Color(0xFF1B1C1A));
      expect(light.surface, light.grey50);
      expect(light.surfaceSecondary, light.grey100);
      expect(light.textPrimary, light.grey900);
      expect(light.textSecondary, light.grey600);
      expect(light.border, light.grey300);
    });

    test('dark values are carried on the same tokens, not sibling tokens', () {
      expect(dark.primary500, const Color(0xFF3FA981));
      expect(dark.grey50, const Color(0xFF17181A));
      expect(dark.grey900, const Color(0xFFF4F5F1));
      expect(dark.surface, dark.grey50);
      expect(dark.textPrimary, dark.grey900);
    });

    test('on-primary flips for dark surfaces', () {
      expect(light.onPrimary, const Color(0xFFFFFFFF));
      expect(dark.onPrimary, const Color(0xFF0A2E22));
    });

    test('on-error role flips for dark surfaces', () {
      expect(light.onError, const Color(0xFFFFFFFF));
      expect(dark.onError, const Color(0xFF17181A));
    });

    test('each semantic scale has the five documented steps', () {
      for (final scale in [
        [
          light.success100,
          light.success300,
          light.success500,
          light.success700,
          light.success900,
        ],
        [
          light.warning100,
          light.warning300,
          light.warning500,
          light.warning700,
          light.warning900,
        ],
        [
          light.error100,
          light.error300,
          light.error500,
          light.error700,
          light.error900,
        ],
        [
          light.info100,
          light.info300,
          light.info500,
          light.info700,
          light.info900,
        ],
        [
          light.accent100,
          light.accent300,
          light.accent500,
          light.accent700,
          light.accent900,
        ],
      ]) {
        expect(scale.toSet(), hasLength(5));
      }
    });

    test('executive semantic anchors match the doc', () {
      expect(light.success500, const Color(0xFF16A34A));
      expect(light.warning500, const Color(0xFFD97706));
      expect(light.error500, const Color(0xFFDC2626));
      expect(light.info500, const Color(0xFF2563EB));
      expect(light.accent500, const Color(0xFFD9643A));
      expect(light.semantic('success'), light.success500);
    });
  });

  group('accessibility: WCAG AA contrast', () {
    test('body text meets 4.5:1 on both surfaces', () {
      expect(
        _contrast(light.textPrimary, light.surface),
        greaterThanOrEqualTo(4.5),
      );
      expect(
        _contrast(light.textSecondary, light.surface),
        greaterThanOrEqualTo(4.5),
      );
      expect(
        _contrast(dark.textPrimary, dark.surface),
        greaterThanOrEqualTo(4.5),
      );
      expect(
        _contrast(dark.textSecondary, dark.surface),
        greaterThanOrEqualTo(4.5),
      );
    });

    test('on-primary text meets 4.5:1 on the primary fill', () {
      expect(
        _contrast(light.onPrimary, light.primary500),
        greaterThanOrEqualTo(4.5),
      );
      expect(
        _contrast(dark.onPrimary, dark.primary500),
        greaterThanOrEqualTo(4.5),
      );
    });

    test('destructive text meets 4.5:1 on the error fill in both modes', () {
      // The fill is dark red in light mode and light red in dark mode, so the
      // on-error role token flips with the mode; white alone fails in dark.
      expect(
        _contrast(light.onError, light.error500),
        greaterThanOrEqualTo(4.5),
      );
      expect(_contrast(dark.onError, dark.error500), greaterThanOrEqualTo(4.5));
    });

    test('status pill text meets 4.5:1 on its tint in both modes', () {
      final pairs = [
        (light.success900, light.success100),
        (light.warning900, light.warning100),
        (light.error900, light.error100),
        (light.info900, light.info100),
        (light.accent900, light.accent100),
        (dark.success900, dark.success100),
        (dark.warning900, dark.warning100),
        (dark.error900, dark.error100),
        (dark.info900, dark.info100),
        (dark.accent900, dark.accent100),
      ];
      for (final (foreground, background) in pairs) {
        expect(_contrast(foreground, background), greaterThanOrEqualTo(4.5));
      }
    });
  });

  group('dimension tokens', () {
    test('spacing, radii, and sizes match the doc', () {
      expect(SabSpacing.xs, 4);
      expect(SabSpacing.xxl, 48);
      expect(SabSpacing.xxxl, 64);
      expect(SabRadii.sm, 4);
      expect(SabRadii.md, 8);
      expect(SabRadii.lg, 12);
      expect(SabRadii.full, 9999);
      expect(SabSizes.buttonHeight, 44);
      expect(SabSizes.inputHeight, 48);
      expect(SabSizes.iconSm, 16);
      expect(SabSizes.iconMd, 24);
      expect(SabSizes.iconLg, 32);
      expect(SabSizes.minTouchTarget, 44);
    });

    test('elevation tokens carry a shadow per step and none is empty', () {
      expect(light.shadows[SabElevation.none], isEmpty);
      for (final step in [
        SabElevation.sm,
        SabElevation.md,
        SabElevation.lg,
        SabElevation.xl,
      ]) {
        expect(light.shadows[step], isNotEmpty);
        expect(dark.shadows[step], isNotEmpty);
      }
    });

    test('motion settles within the documented success window', () {
      expect(SabMotion.emphasized.inMilliseconds, inInclusiveRange(400, 600));
      expect(SabMotion.pendingLoop, const Duration(seconds: 2));
    });
  });
}
