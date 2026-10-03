import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/design_system/icons.dart';
import 'package:sabi_mobile/design_system/sab_art.dart';
import 'package:sabi_mobile/design_system/tokens.dart';

/// Guards the asset/token integration (D-014, D-015, D-016): one runtime file
/// loaded by artboard name, a bundled brand typeface, and every semantic icon
/// name resolving to an artboard and a bridge glyph.
void main() {
  group('single runtime file (D-016)', () {
    test('every artboard names the same one file', () {
      expect(sabRiveFile, 'assets/sabi.riv');
      for (final artboard in SabArtboard.values) {
        expect(artboard.artboard, isNotEmpty);
      }
    });

    test('only the state stings are animated and carry a state machine', () {
      final animated = {
        for (final a in SabArtboard.values)
          if (a.isAnimated) a.artboard: a.stateMachine,
      };
      expect(animated.keys, containsAll(['Success', 'Pending', 'Error']));
      for (final machine in animated.values) {
        expect(machine, isNotNull);
      }
      expect(SabArtboard.brandMark.isAnimated, isFalse);
      expect(SabArtboard.emptyState.isAnimated, isFalse);
      expect(SabArtboard.offline.isAnimated, isFalse);
    });

    test('every icon name resolves to an Icon* artboard', () {
      for (final icon in SabIcon.values) {
        expect(icon.artboard, startsWith('Icon'));
      }
    });
  });

  group('custom icon set (D-015)', () {
    test(
      'the semantics expose each nav, status, channel, and action glyph',
      () {
        expect(SabIcons.home.artboard, 'IconHome');
        expect(SabIcons.statusFailed.artboard, 'IconStatusFailed');
        expect(SabIcons.channelWhatsapp.artboard, 'IconChannelWhatsapp');
        expect(SabIcons.paymentMethod.artboard, 'IconPaymentMethod');
      },
    );

    testWidgets('a known artboard maps to a Material bridge glyph', (
      tester,
    ) async {
      expect(materialIconForArtboard('IconCheck'), Icons.check_rounded);
    });

    test(
      'an unknown artboard resolves to a visible placeholder, not a blank',
      () {
        expect(
          materialIconForArtboard('IconNotInTheBuild'),
          Icons.help_outline_rounded,
        );
      },
    );
  });

  group('brand typeface (D-014)', () {
    test('the typography tokens declare the bundled families', () {
      expect(SabTypography.fontFamily, 'Inter');
      expect(SabTypography.monoFamily, 'JetBrainsMono');
      expect(SabTypography.body.fontFamily, 'Inter');
      expect(SabTypography.mono.fontFamily, 'JetBrainsMono');
      expect(SabTypography.monoCode.fontFamily, 'JetBrainsMono');
    });
  });

  /// Guards the native launcher-icon and launch-screen generation: the configs
  /// exist and drive the packages from the brand assets, and the generated
  /// native outputs are present (the stock Flutter placeholders are gone).
  group('native icon and splash generation', () {
    File source(String relative) => File(relative);

    test('the generator configs exist and reference the brand assets', () {
      final icons = source('flutter_launcher_icons.yaml');
      final splash = source('flutter_native_splash.yaml');
      expect(icons.existsSync(), isTrue);
      expect(splash.existsSync(), isTrue);

      final iconsText = icons.readAsStringSync();
      expect(iconsText, contains('assets/app-icon.png'));
      expect(iconsText, contains('assets/native/adaptive-foreground.png'));

      final splashText = splash.readAsStringSync();
      expect(splashText, contains('assets/native/splash-mark.png'));
      expect(splashText, contains('assets/native/splash-mark-dark.png'));
      expect(splashText, contains('#FAF8F4')); // warm off-white surface
      expect(splashText, contains('#17181A')); // dark surface
    });

    test('the generated Android icon set is present across every density', () {
      for (final density in ['mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi']) {
        expect(
          source(
            'android/app/src/main/res/mipmap-$density/ic_launcher.png',
          ).existsSync(),
          isTrue,
          reason: 'launcher icon missing for $density',
        );
      }
      // Adaptive icon (foreground/background layers) and the Android 12+ logo.
      expect(
        source(
          'android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml',
        ).existsSync(),
        isTrue,
      );
      expect(
        source(
          'android/app/src/main/res/drawable-xxxhdpi/'
          'ic_launcher_foreground.png',
        ).existsSync(),
        isTrue,
      );
      expect(
        source(
          'android/app/src/main/res/drawable-xxxhdpi/android12splash.png',
        ).existsSync(),
        isTrue,
      );
      // Dark-mode variants exist for the splash.
      expect(
        source(
          'android/app/src/main/res/drawable-night-xxxhdpi/splash.png',
        ).existsSync(),
        isTrue,
      );
    });

    test('the generated iOS icon set and launch images are present', () {
      expect(
        source(
          'ios/Runner/Assets.xcassets/AppIcon.appiconset/'
          'Icon-App-1024x1024@1x.png',
        ).existsSync(),
        isTrue,
      );
      expect(
        source(
          'ios/Runner/Assets.xcassets/LaunchImage.imageset/'
          'LaunchImage@3x.png',
        ).existsSync(),
        isTrue,
      );
      expect(
        source(
          'ios/Runner/Assets.xcassets/LaunchImage.imageset/'
          'LaunchImageDark@3x.png',
        ).existsSync(),
        isTrue,
      );
    });
  });
}
