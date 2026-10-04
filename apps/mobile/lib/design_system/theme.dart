import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'tokens.dart';

/// The system status and navigation bar style for a token palette.
///
/// Both bars carry [SabColorTokens.surface] rather than a transparent bar:
/// below API 35, without enforced edge-to-edge, Android paints its own window
/// background behind a transparent bar, so it read white or black by device
/// theme instead of the brand surface. On API 35+ the bar colour is ignored
/// under enforced edge-to-edge, and the theme's [ThemeData.scaffoldBackgroundColor]
/// shows the same token surface behind the bar. Icon brightness follows the
/// surface luminance, the contrast scrims are disabled so the surface is never
/// toned to a different colour, and every field is token-derived rather than
/// Material's default black bar (branding.md, "Color Palette"; NFR-030;
/// decision D-037).
SystemUiOverlayStyle sabSystemOverlayStyle(SabColorTokens colors) {
  // Light surfaces take dark icons and dark surfaces light icons, so the icon
  // brightness follows the surface luminance rather than the theme flag.
  final surfaceIsLight = colors.surface.computeLuminance() > 0.5;
  final iconBrightness = surfaceIsLight ? Brightness.dark : Brightness.light;
  return SystemUiOverlayStyle(
    statusBarColor: colors.surface,
    // iOS reads the background brightness, which is the inverse of its icons.
    statusBarBrightness: surfaceIsLight ? Brightness.light : Brightness.dark,
    statusBarIconBrightness: iconBrightness,
    systemStatusBarContrastEnforced: false,
    systemNavigationBarColor: colors.surface,
    systemNavigationBarDividerColor: colors.surface,
    systemNavigationBarIconBrightness: iconBrightness,
    systemNavigationBarContrastEnforced: false,
  );
}

/// Applies the token system bar style to a surface that has no app bar, such as
/// the Welcome and Sign In screens. A screen with an [AppBar] is covered by
/// [AppBarTheme.systemOverlayStyle] already; nesting is harmless because the
/// framework lets the region nearest the bar win.
class SabSystemBars extends StatelessWidget {
  const SabSystemBars({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: sabSystemOverlayStyle(SabColorTokens.of(context)),
      child: child,
    );
  }
}

/// Builds the Material theme from the Sabi tokens. Both light and dark themes
/// come from the same token set, so a screen styled against tokens renders in
/// either mode without a second stylesheet.
ThemeData buildSabTheme(Brightness brightness) {
  final colors = brightness == Brightness.dark
      ? SabColorTokens.dark
      : SabColorTokens.light;
  final textTheme = SabTypography.textTheme(colors);
  final scheme = ColorScheme(
    brightness: brightness,
    primary: colors.primary500,
    onPrimary: colors.onPrimary,
    primaryContainer: colors.primary100,
    onPrimaryContainer: colors.primary900,
    secondary: colors.primary700,
    onSecondary: colors.onPrimary,
    surface: colors.surface,
    onSurface: colors.textPrimary,
    surfaceContainerHighest: colors.surfaceSecondary,
    onSurfaceVariant: colors.textSecondary,
    error: colors.error500,
    onError: colors.onError,
    errorContainer: colors.error100,
    onErrorContainer: colors.error900,
    outline: colors.border,
    outlineVariant: colors.grey200,
    shadow: colors.grey900,
    scrim: colors.grey900,
    inverseSurface: colors.textPrimary,
    onInverseSurface: colors.surface,
    inversePrimary: colors.primary300,
  );

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: colors.surface,
    canvasColor: colors.surface,
    dividerColor: colors.border,
    splashFactory: InkSparkle.splashFactory,
    textTheme: textTheme,
    primaryTextTheme: textTheme,
    appBarTheme: AppBarTheme(
      backgroundColor: colors.surface,
      foregroundColor: colors.textPrimary,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: SabTypography.h3.copyWith(color: colors.textPrimary),
      iconTheme: IconThemeData(
        color: colors.textPrimary,
        size: SabSizes.iconMd,
      ),
      systemOverlayStyle: sabSystemOverlayStyle(colors),
    ),
    dividerTheme: DividerThemeData(
      color: colors.border,
      thickness: 1,
      space: 1,
    ),
    iconTheme: IconThemeData(
      color: colors.textSecondary,
      size: SabSizes.iconMd,
    ),
    listTileTheme: ListTileThemeData(
      iconColor: colors.textSecondary,
      textColor: colors.textPrimary,
      selectedColor: colors.primary700,
      selectedTileColor: colors.primary100,
      contentPadding: const EdgeInsets.symmetric(
        horizontal: SabSpacing.md,
        vertical: SabSpacing.sm,
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
    ),
    bottomNavigationBarTheme: BottomNavigationBarThemeData(
      backgroundColor: colors.surface,
      selectedItemColor: colors.primary500,
      unselectedItemColor: colors.textSecondary,
      selectedLabelStyle: SabTypography.caption,
      unselectedLabelStyle: SabTypography.caption,
      type: BottomNavigationBarType.fixed,
      elevation: 0,
      showUnselectedLabels: true,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: colors.primary500,
        foregroundColor: colors.onPrimary,
        disabledBackgroundColor: colors.grey200,
        disabledForegroundColor: colors.textSecondary,
        minimumSize: const Size(0, SabSizes.buttonHeight),
        padding: SabSizes.buttonPadding,
        textStyle: SabTypography.body.copyWith(fontWeight: FontWeight.w600),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(SabRadii.md),
        ),
        elevation: 0,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: colors.primary500,
        minimumSize: const Size(0, SabSizes.buttonHeight),
        padding: SabSizes.buttonPadding,
        textStyle: SabTypography.body.copyWith(fontWeight: FontWeight.w600),
        side: BorderSide(color: colors.primary500, width: 1.5),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(SabRadii.md),
        ),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: colors.primary500,
        minimumSize: const Size(0, SabSizes.buttonHeight),
        padding: const EdgeInsets.symmetric(
          horizontal: SabSpacing.md,
          vertical: SabSpacing.sm,
        ),
        textStyle: SabTypography.body.copyWith(fontWeight: FontWeight.w600),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(SabRadii.md),
        ),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: colors.surfaceSecondary,
      hintStyle: SabTypography.body.copyWith(color: colors.textSecondary),
      labelStyle: SabTypography.body.copyWith(color: colors.textSecondary),
      helperStyle: SabTypography.bodySmall.copyWith(
        color: colors.textSecondary,
      ),
      errorStyle: SabTypography.bodySmall.copyWith(color: colors.error500),
      contentPadding: const EdgeInsets.symmetric(
        horizontal: SabSpacing.md,
        vertical: SabSpacing.md,
      ),
      constraints: const BoxConstraints(minHeight: SabSizes.inputHeight),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(SabRadii.md),
        borderSide: BorderSide(color: colors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(SabRadii.md),
        borderSide: BorderSide(color: colors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(SabRadii.md),
        borderSide: BorderSide(color: colors.primary500, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(SabRadii.md),
        borderSide: BorderSide(color: colors.error500),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(SabRadii.md),
        borderSide: BorderSide(color: colors.error500, width: 2),
      ),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: colors.surface,
      surfaceTintColor: Colors.transparent,
      modalBackgroundColor: colors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(SabRadii.lg)),
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: colors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(SabRadii.lg),
      ),
      titleTextStyle: SabTypography.h3.copyWith(color: colors.textPrimary),
      contentTextStyle: SabTypography.body.copyWith(
        color: colors.textSecondary,
      ),
    ),
    cardTheme: CardThemeData(
      color: colors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(SabRadii.md),
        side: BorderSide(color: colors.border),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: colors.textPrimary,
      contentTextStyle: SabTypography.body.copyWith(color: colors.surface),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(SabRadii.md),
      ),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: colors.primary500,
      linearTrackColor: colors.grey200,
      circularTrackColor: colors.grey200,
    ),
    dropdownMenuTheme: DropdownMenuThemeData(
      textStyle: SabTypography.body.copyWith(color: colors.textPrimary),
      menuStyle: MenuStyle(
        backgroundColor: WidgetStatePropertyAll(colors.surface),
        surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
      ),
    ),
  );
}
