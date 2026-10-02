import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/design_system/sab_art.dart';

/// Guards the art layer's state behaviour: reduced motion degrades the animated
/// stings to a static result (branding.md, "Accessibility"; ASSETS.md motion
/// spec), so motion never carries the only meaning.
void main() {
  Future<void> pumpArt(
    WidgetTester tester,
    SabArtboard artboard, {
    required bool reduceMotion,
  }) async {
    await tester.pumpWidget(
      MediaQuery(
        data: MediaQueryData(disableAnimations: reduceMotion),
        child: Directionality(
          textDirection: TextDirection.ltr,
          child: Center(
            child: SabArt(artboard: artboard, size: 96, semanticLabel: 'State'),
          ),
        ),
      ),
    );
  }

  testWidgets('reduced motion renders a static result for an animated sting', (
    tester,
  ) async {
    await pumpArt(tester, SabArtboard.success, reduceMotion: true);
    // No Rive decoding runs under reduced motion; a token-coloured static icon
    // stands in and the semantics label still announces the state.
    expect(find.byType(Icon), findsOneWidget);
    expect(find.bySemanticsLabel('State'), findsOneWidget);
  });
}
