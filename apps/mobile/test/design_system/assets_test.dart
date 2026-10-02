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
}
