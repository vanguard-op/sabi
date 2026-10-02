import 'package:flutter/material.dart';
import 'package:rive/rive.dart';

import 'tokens.dart';

/// The eight artboards delivered by the visual artist (ASSETS.md A-001–A-008),
/// mapped to the file and state machine the client loads. Slots are named after
/// the ledger, not the screen that happens to use them.
enum SabArtboard {
  brandMark('assets/brand-mark/master.riv', 'BrandMark', null),
  emptyState('assets/illustrations/empty-state.riv', 'EmptyState', null),
  offline('assets/illustrations/offline.riv', 'Offline', null),
  success('assets/animations/success.riv', 'Success', 'Success SM'),
  pending('assets/animations/pending.riv', 'Pending', 'Pending SM'),
  error('assets/animations/error.riv', 'Error', 'Error SM');

  const SabArtboard(this.asset, this.artboard, this.stateMachine);

  final String asset;
  final String artboard;

  /// Null for the static artboards; the three state stings each carry a named
  /// state machine.
  final String? stateMachine;

  bool get isAnimated => stateMachine != null;
}

/// Opts a subtree into static-only art rendering. Production leaves this at the
/// default; widget tests set it so screens render without decoding Rive files.
class SabArtMode extends InheritedWidget {
  const SabArtMode({super.key, required this.staticOnly, required super.child});

  final bool staticOnly;

  static bool staticOnlyOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<SabArtMode>()?.staticOnly ??
      false;

  @override
  bool updateShouldNotify(SabArtMode oldWidget) =>
      oldWidget.staticOnly != staticOnly;
}

/// Wraps art in the semantics tree: labelled art is announced as an image;
/// unlabelled art is decorative and hidden from assistive tech, so a screen
/// reader never lands on an unnamed image.
Widget _artSemantics(String? label, Widget child) {
  if (label == null) return ExcludeSemantics(child: child);
  return Semantics(label: label, image: true, child: child);
}

/// Renders a Sabi artboard at [size] logical pixels.
///
/// Honours reduced motion: the three payment-state stings degrade to a static
/// token-coloured result rather than looping, and meaning is never carried by
/// motion alone. Falls back to the same static result if the artwork fails to
/// decode, so a missing or broken asset never blocks a task.
class SabArt extends StatefulWidget {
  const SabArt({
    super.key,
    required this.artboard,
    required this.size,
    this.semanticLabel,
  });

  final SabArtboard artboard;
  final double size;
  final String? semanticLabel;

  @override
  State<SabArt> createState() => _SabArtState();
}

class _SabArtState extends State<SabArt> {
  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final staticOnly = SabArtMode.staticOnlyOf(context);
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    final renderStatic =
        staticOnly || (widget.artboard.isAnimated && reduceMotion);

    if (renderStatic) {
      return _ArtFallback(
        artboard: widget.artboard,
        size: widget.size,
        colors: colors,
        semanticLabel: widget.semanticLabel,
      );
    }

    final stateMachine = widget.artboard.stateMachine;
    return _artSemantics(
      widget.semanticLabel,
      SizedBox(
        width: widget.size,
        height: widget.size,
        child: RiveWidgetBuilder(
          fileLoader: FileLoader.fromAsset(
            widget.artboard.asset,
            riveFactory: Factory.rive,
          ),
          artboardSelector: ArtboardSelector.byName(widget.artboard.artboard),
          stateMachineSelector: stateMachine == null
              ? const StateMachineDefault()
              : StateMachineSelector.byName(stateMachine),
          builder: (context, state) => switch (state) {
            RiveLoaded(:final controller) => RiveWidget(
              controller: controller,
              fit: Fit.contain,
            ),
            RiveFailed() => _ArtFallback(
              artboard: widget.artboard,
              size: widget.size,
              colors: colors,
              semanticLabel: widget.semanticLabel,
            ),
            RiveLoading() => SizedBox(width: widget.size, height: widget.size),
          },
        ),
      ),
    );
  }
}

/// Static stand-in used for reduced motion, tests, and decode failures. It
/// carries the artboard's silhouette in the brand's duotone so a screen still
/// reads as designed without the runtime artwork.
class _ArtFallback extends StatelessWidget {
  const _ArtFallback({
    required this.artboard,
    required this.size,
    required this.colors,
    this.semanticLabel,
  });

  final SabArtboard artboard;
  final double size;
  final SabColorTokens colors;
  final String? semanticLabel;

  IconData get _icon => switch (artboard) {
    SabArtboard.brandMark => Icons.chat_bubble_outline,
    SabArtboard.emptyState => Icons.receipt_long_outlined,
    SabArtboard.offline => Icons.wifi_off_outlined,
    SabArtboard.success => Icons.check_circle_outline,
    SabArtboard.pending => Icons.schedule_outlined,
    SabArtboard.error => Icons.error_outline,
  };

  Color get _tint => switch (artboard) {
    SabArtboard.success => colors.success500,
    SabArtboard.pending => colors.warning500,
    SabArtboard.error => colors.error500,
    _ => colors.primary500,
  };

  @override
  Widget build(BuildContext context) {
    return _artSemantics(
      semanticLabel,
      SizedBox(
        width: size,
        height: size,
        child: Icon(_icon, size: size * 0.62, color: _tint),
      ),
    );
  }
}
