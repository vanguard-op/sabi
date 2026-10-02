import 'package:flutter/material.dart';

/// Sabi design tokens.
///
/// The single source of truth for colour, spacing, sizing, type, and motion,
/// implementing `docs/Sabi/branding.md` ("Design System", "Accessibility",
/// "Asset Style Guide"). Call sites read tokens from here (or from a theme built
/// here); no call site hardcodes a design value.
///
/// Colour is declared as light/dark pairs in one token — there are no `-dark`
/// sibling tokens. The documented anchors are the only literal hex values; the
/// intermediate shades the docs ask for are interpolated deterministically from
/// those anchors by [_ramp] and [_semanticScale].
@immutable
class SabColorTokens {
  const SabColorTokens._(
    this._primary,
    this._grey,
    this._semantic, {
    required this.surface,
    required this.surfaceSecondary,
    required this.textPrimary,
    required this.textSecondary,
    required this.border,
    required this.onPrimary,
    required this.shadows,
  });

  final Map<int, Color> _primary;
  final Map<int, Color> _grey;
  final Map<String, Map<int, Color>> _semantic;

  /// Semantic role: page background (`grey-50`).
  final Color surface;

  /// Semantic role: secondary surfaces and input backgrounds (`grey-100`).
  final Color surfaceSecondary;

  /// Semantic role: primary text (`grey-900`).
  final Color textPrimary;

  /// Semantic role: secondary text (`grey-600`).
  final Color textSecondary;

  /// Semantic role: borders and dividers (`grey-300`).
  final Color border;

  /// Semantic role: text and icons on a primary fill.
  final Color onPrimary;

  /// The brand's flat white, used for text and icons on an error fill. It is
  /// constant across light and dark (branding.md, Component Tokens — Destructive).
  static const Color knockout = Color(0xFFFFFFFF);

  /// Elevation shadows by [SabElevation].
  final Map<SabElevation, List<BoxShadow>> shadows;

  // --- Primary scale (9 shades, 100–900) --------------------------------

  Color get primary100 => _primary[100]!;
  Color get primary200 => _primary[200]!;
  Color get primary300 => _primary[300]!;
  Color get primary400 => _primary[400]!;
  Color get primary500 => _primary[500]!;
  Color get primary600 => _primary[600]!;
  Color get primary700 => _primary[700]!;
  Color get primary800 => _primary[800]!;
  Color get primary900 => _primary[900]!;

  // --- Warm grey scale (50–900) -----------------------------------------

  Color get grey50 => _grey[50]!;
  Color get grey100 => _grey[100]!;
  Color get grey200 => _grey[200]!;
  Color get grey300 => _grey[300]!;
  Color get grey400 => _grey[400]!;
  Color get grey500 => _grey[500]!;
  Color get grey600 => _grey[600]!;
  Color get grey700 => _grey[700]!;
  Color get grey800 => _grey[800]!;
  Color get grey900 => _grey[900]!;

  // --- Semantic and accent 5-shade scales (100/300/500/700/900) ----------

  Color get success100 => _semantic['success']![100]!;
  Color get success300 => _semantic['success']![300]!;
  Color get success500 => _semantic['success']![500]!;
  Color get success700 => _semantic['success']![700]!;
  Color get success900 => _semantic['success']![900]!;

  Color get warning100 => _semantic['warning']![100]!;
  Color get warning300 => _semantic['warning']![300]!;
  Color get warning500 => _semantic['warning']![500]!;
  Color get warning700 => _semantic['warning']![700]!;
  Color get warning900 => _semantic['warning']![900]!;

  Color get error100 => _semantic['error']![100]!;
  Color get error300 => _semantic['error']![300]!;
  Color get error500 => _semantic['error']![500]!;
  Color get error700 => _semantic['error']![700]!;
  Color get error900 => _semantic['error']![900]!;

  Color get info100 => _semantic['info']![100]!;
  Color get info300 => _semantic['info']![300]!;
  Color get info500 => _semantic['info']![500]!;
  Color get info700 => _semantic['info']![700]!;
  Color get info900 => _semantic['info']![900]!;

  Color get accent100 => _semantic['accent']![100]!;
  Color get accent300 => _semantic['accent']![300]!;
  Color get accent500 => _semantic['accent']![500]!;
  Color get accent700 => _semantic['accent']![700]!;
  Color get accent900 => _semantic['accent']![900]!;

  /// Resolves the palette for the current [Brightness].
  static SabColorTokens of(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? dark : light;

  /// The 500 shade for a semantic scale name (`success`, `warning`, `error`,
  /// `info`, `accent`).
  Color semantic(String name) => _semantic[name]![500]!;

  // --- Documented anchors -------------------------------------------------

  // primary.md anchors (light / dark).
  static const _primaryLightAnchors = <int, int>{
    100: 0xFFE3F2EC,
    300: 0xFF8FCDB2,
    500: 0xFF12805C,
    700: 0xFF0E5940,
    900: 0xFF0A3829,
  };
  static const _primaryDarkAnchors = <int, int>{
    100: 0xFF14382B,
    300: 0xFF236E54,
    500: 0xFF3FA981,
    700: 0xFF8AD0B6,
    900: 0xFFC6ECDE,
  };

  // grey.md anchors (light / dark).
  static const _greyLightAnchors = <int, int>{
    50: 0xFFFAF8F4,
    100: 0xFFEEEFE8,
    300: 0xFFC6C9BE,
    600: 0xFF5B5F54,
    900: 0xFF1B1C1A,
  };
  static const _greyDarkAnchors = <int, int>{
    50: 0xFF17181A,
    100: 0xFF202219,
    300: 0xFF3F4238,
    600: 0xFFA8AC9E,
    900: 0xFFF4F5F1,
  };

  // semantic 500 anchors (light / dark).
  static const _semanticLightAnchors = <String, int>{
    'success': 0xFF16A34A,
    'warning': 0xFFD97706,
    'error': 0xFFDC2626,
    'info': 0xFF2563EB,
    'accent': 0xFFD9643A,
  };
  static const _semanticDarkAnchors = <String, int>{
    'success': 0xFF4ADE80,
    'warning': 0xFFFBBF24,
    'error': 0xFFF87171,
    'info': 0xFF60A5FA,
    'accent': 0xFFF0A088,
  };

  static const _primarySteps = <int>[
    100,
    200,
    300,
    400,
    500,
    600,
    700,
    800,
    900,
  ];
  static const _greySteps = <int>[
    50,
    100,
    200,
    300,
    400,
    500,
    600,
    700,
    800,
    900,
  ];

  static final SabColorTokens light = _build(Brightness.light);
  static final SabColorTokens dark = _build(Brightness.dark);

  static SabColorTokens _build(Brightness brightness) {
    final isDark = brightness == Brightness.dark;
    final primary = _ramp(
      isDark ? _primaryDarkAnchors : _primaryLightAnchors,
      _primarySteps,
    );
    final grey = _ramp(
      isDark ? _greyDarkAnchors : _greyLightAnchors,
      _greySteps,
    );
    final semantic = <String, Map<int, Color>>{
      for (final entry
          in (isDark ? _semanticDarkAnchors : _semanticLightAnchors).entries)
        entry.key: _semanticScale(entry.value, isDark),
    };
    return SabColorTokens._(
      primary,
      grey,
      semantic,
      surface: grey[50]!,
      surfaceSecondary: grey[100]!,
      textPrimary: grey[900]!,
      textSecondary: grey[600]!,
      border: grey[300]!,
      onPrimary: isDark ? const Color(0xFF0A2E22) : const Color(0xFFFFFFFF),
      shadows: _shadowScale(isDark),
    );
  }
}

/// Elevation steps; each resolves to a token shadow list per brightness.
enum SabElevation { none, sm, md, lg, xl }

// --- Colour math -----------------------------------------------------------

const Color _white = Color(0xFFFFFFFF);
const Color _black = Color(0xFF000000);

Color _mix(Color a, Color b, double t) => Color.lerp(a, b, t)!;

/// Fills [steps] across the documented [anchors], interpolating any step the
/// docs leave implicit between its nearest lower and upper anchors.
Map<int, Color> _ramp(Map<int, int> anchors, List<int> steps) {
  final keys = anchors.keys.toList()..sort();
  final out = <int, Color>{};
  for (final step in steps) {
    if (anchors.containsKey(step)) {
      out[step] = Color(anchors[step]!);
      continue;
    }
    final lower = keys.lastWhere((k) => k < step, orElse: () => keys.first);
    final upper = keys.firstWhere((k) => k > step, orElse: () => keys.last);
    if (lower == upper) {
      out[step] = Color(anchors[lower]!);
      continue;
    }
    out[step] = _mix(
      Color(anchors[lower]!),
      Color(anchors[upper]!),
      (step - lower) / (upper - lower),
    );
  }
  return out;
}

/// Builds the 5-shade semantic scale from its 500 anchor. 100 tints a
/// background, 300 is a softened accent, 900 is readable text on the tint.
/// In dark mode the direction reverses so 100 stays a dark tint and 900 stays
/// light text.
Map<int, Color> _semanticScale(int anchor, bool isDark) {
  final a = Color(anchor);
  if (isDark) {
    return {
      100: _mix(a, _black, 0.62),
      300: _mix(a, _black, 0.34),
      500: a,
      700: _mix(a, _white, 0.25),
      900: _mix(a, _white, 0.52),
    };
  }
  return {
    100: _mix(a, _white, 0.86),
    300: _mix(a, _white, 0.55),
    500: a,
    700: _mix(a, _black, 0.30),
    900: _mix(a, _black, 0.55),
  };
}

Map<SabElevation, List<BoxShadow>> _shadowScale(bool isDark) {
  BoxShadow only(double alpha, double y, double blur) => BoxShadow(
    color: _black.withValues(alpha: alpha),
    offset: Offset(0, y),
    blurRadius: blur,
  );
  return {
    SabElevation.none: const [],
    SabElevation.sm: [only(isDark ? 0.40 : 0.05, 1, 2)],
    SabElevation.md: [only(isDark ? 0.50 : 0.07, 4, isDark ? 8 : 6)],
    SabElevation.lg: [only(isDark ? 0.65 : 0.10, 10, isDark ? 30 : 25)],
    SabElevation.xl: [only(isDark ? 0.70 : 0.15, 24, isDark ? 60 : 50)],
  };
}

/// Spacing scale (`branding.md`, "Spacing").
abstract final class SabSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
  static const double xxl = 48;
  static const double xxxl = 64;
}

/// Corner radii (`branding.md`, "Sizing").
abstract final class SabRadii {
  static const double sm = 4;
  static const double md = 8;
  static const double lg = 12;
  static const double full = 9999;
}

/// Fixed component sizes (`branding.md`, "Sizing"). `buttonHeight` is also the
/// minimum touch target from "Accessibility". The art and content sizes are
/// composition constants the token map does not name; they live here so no call
/// site hardcodes a layout dimension.
abstract final class SabSizes {
  static const double buttonHeight = 44;
  static const double inputHeight = 48;
  static const double iconSm = 16;
  static const double iconMd = 24;
  static const double iconLg = 32;
  static const double minTouchTarget = 44;

  /// Brand mark on Welcome.
  static const double artBrandMark = 96;

  /// Brand mark on Sign In.
  static const double artBrandMarkSmall = iconLg * 2.25;

  /// Empty-state illustration.
  static const double artEmptyState = SabSpacing.xxxl * 1.75;

  /// Error-state illustration.
  static const double artError = SabSpacing.xxxl * 1.5;

  /// Reading column for auth screens and sheets.
  static const double contentMaxWidth = 420;

  /// Label column in the Confirmation Summary block.
  static const double summaryLabelWidth = 96;

  /// Horizontal/vertical padding for buttons per the component token table.
  static const EdgeInsets buttonPadding = EdgeInsets.symmetric(
    horizontal: SabSpacing.lg,
    vertical: SabSpacing.md,
  );
}

/// Motion tokens (`branding.md`, "Motion Direction"); timing is never hardcoded
/// at a call site. State animations settle in 400–600ms and never bounce.
abstract final class SabMotion {
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration base = Duration(milliseconds: 250);
  static const Duration emphasized = Duration(milliseconds: 500);
  static const Duration pendingLoop = Duration(seconds: 2);

  /// One half-cycle of the loading skeleton's opacity pulse. Slow and calm, so
  /// the placeholder reads as a wait rather than a flash.
  static const Duration skeletonPulse = Duration(milliseconds: 1100);

  static const Curve standard = Curves.easeInOut;
  static const Curve decelerate = Curves.easeOutCubic;
  static const Curve accelerate = Curves.easeInCubic;
}

/// The type scale (`branding.md`, "Typography"). Inter is the declared family
/// and the platform sans is the documented fallback; the font assets are not in
/// the ledger yet, so the fallback is what ships today.
abstract final class SabTypography {
  static const String fontFamily = 'Inter';
  static const String monoFamily = 'JetBrainsMono';

  static const TextStyle display = TextStyle(
    fontFamily: fontFamily,
    fontSize: 40,
    fontWeight: FontWeight.w700,
    height: 1.2,
  );
  static const TextStyle h1 = TextStyle(
    fontFamily: fontFamily,
    fontSize: 32,
    fontWeight: FontWeight.w700,
    height: 1.3,
  );
  static const TextStyle h2 = TextStyle(
    fontFamily: fontFamily,
    fontSize: 24,
    fontWeight: FontWeight.w600,
    height: 1.35,
  );
  static const TextStyle h3 = TextStyle(
    fontFamily: fontFamily,
    fontSize: 20,
    fontWeight: FontWeight.w600,
    height: 1.4,
  );
  static const TextStyle bodyLarge = TextStyle(
    fontFamily: fontFamily,
    fontSize: 18,
    fontWeight: FontWeight.w400,
    height: 1.5,
  );
  static const TextStyle body = TextStyle(
    fontFamily: fontFamily,
    fontSize: 16,
    fontWeight: FontWeight.w400,
    height: 1.5,
  );
  static const TextStyle bodySmall = TextStyle(
    fontFamily: fontFamily,
    fontSize: 14,
    fontWeight: FontWeight.w400,
    height: 1.5,
  );
  static const TextStyle caption = TextStyle(
    fontFamily: fontFamily,
    fontSize: 12,
    fontWeight: FontWeight.w500,
    height: 1.4,
  );
  static const TextStyle mono = TextStyle(
    fontFamily: monoFamily,
    fontSize: 14,
    fontWeight: FontWeight.w400,
    height: 1.5,
  );

  /// Monospace for a code the user reads character by character (recovery code,
  /// meter numbers).
  static const TextStyle monoCode = TextStyle(
    fontFamily: monoFamily,
    fontSize: 14,
    fontWeight: FontWeight.w600,
    height: 1.5,
    letterSpacing: 1.5,
  );

  /// Maps the tokens onto Material's [TextTheme] slots so platform widgets and
  /// custom ones draw from the same scale.
  static TextTheme textTheme(SabColorTokens colors) => TextTheme(
    displaySmall: display.copyWith(color: colors.textPrimary),
    headlineMedium: h1.copyWith(color: colors.textPrimary),
    headlineSmall: h2.copyWith(color: colors.textPrimary),
    titleLarge: h3.copyWith(color: colors.textPrimary),
    bodyLarge: bodyLarge.copyWith(color: colors.textPrimary),
    bodyMedium: body.copyWith(color: colors.textPrimary),
    bodySmall: bodySmall.copyWith(color: colors.textSecondary),
    labelSmall: caption.copyWith(color: colors.textSecondary),
    labelLarge: body.copyWith(
      color: colors.textPrimary,
      fontWeight: FontWeight.w600,
    ),
  );
}
