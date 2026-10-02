import 'package:flutter/material.dart';
import 'package:rive/rive.dart';

import 'tokens.dart';

/// The runtime graphics delivered by the visual artist (ASSETS.md A-001–A-009),
/// each loaded by artboard name from the single runtime file `assets/sabi.riv`.
///
/// Per **D-016** there is one `.riv` file; the enum never names a per-slot file
/// and no artwork is duplicated. Slots are named after the ledger, not the
/// screen that happens to use them.
enum SabArtboard {
  brandMark('BrandMark', null),
  emptyState('EmptyState', null),
  offline('Offline', null),
  success('Success', 'Success SM'),
  pending('Pending', 'Pending SM'),
  error('Error', 'Error SM');

  const SabArtboard(this.artboard, this.stateMachine);

  /// The artboard name inside [sabRiveFile].
  final String artboard;

  /// Null for the static artboards; the three state stings each carry a named
  /// state machine.
  final String? stateMachine;

  bool get isAnimated => stateMachine != null;
}

/// The one runtime file every artboard is loaded from (D-016, ASSETS.md).
const String sabRiveFile = 'assets/sabi.riv';

/// A shared loader so the file is decoded once and reused by [SabArt] and
/// [SabIconArt]; the underlying [File] is disposed when the app tears the
/// loader down. Kept private to the art layer.
final FileLoader _sabFileLoader = FileLoader.fromAsset(
  sabRiveFile,
  riveFactory: Factory.rive,
);

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

    return _RiveArtboard(
      artboard: widget.artboard.artboard,
      stateMachine: widget.artboard.stateMachine,
      size: widget.size,
      semanticLabel: widget.semanticLabel,
      fallback: _ArtFallback(
        artboard: widget.artboard,
        size: widget.size,
        colors: colors,
        semanticLabel: widget.semanticLabel,
      ),
    );
  }
}

/// Renders one named artboard from the single runtime file at [size] onto a
/// [tint] colour through a colour filter, so one artboard serves every state
/// (ASSETS.md A-009).
///
/// [artboardName] is the raw artboard name; the caller passes a value that is
/// guaranteed to exist in [sabRiveFile].
class SabIconArt extends StatelessWidget {
  const SabIconArt({
    super.key,
    required this.artboardName,
    required this.size,
    required this.tint,
    this.semanticLabel,
  });

  final String artboardName;
  final double size;
  final Color tint;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final staticOnly = SabArtMode.staticOnlyOf(context);
    final fallback = _IconFallback(
      name: artboardName,
      size: size,
      tint: tint,
      semanticLabel: semanticLabel,
    );
    if (staticOnly) return fallback;
    return _RiveArtboard(
      artboard: artboardName,
      stateMachine: null,
      size: size,
      semanticLabel: semanticLabel,
      tint: tint,
      fallback: fallback,
    );
  }
}

/// Loads a named artboard from the shared runtime file and paints it. Any
/// decode, artboard-selection, or paint failure yields [fallback] so a task is
/// never blocked by artwork.
class _RiveArtboard extends StatelessWidget {
  const _RiveArtboard({
    required this.artboard,
    required this.stateMachine,
    required this.size,
    required this.fallback,
    this.semanticLabel,
    this.tint,
  });

  final String artboard;
  final String? stateMachine;
  final double size;
  final Widget fallback;
  final String? semanticLabel;
  final Color? tint;

  @override
  Widget build(BuildContext context) {
    final machine = stateMachine;
    return _artSemantics(
      semanticLabel,
      SizedBox(
        width: size,
        height: size,
        child: RiveWidgetBuilder(
          fileLoader: _sabFileLoader,
          artboardSelector: ArtboardSelector.byName(artboard),
          stateMachineSelector: machine == null
              ? const StateMachineDefault()
              : StateMachineSelector.byName(machine),
          builder: (context, state) => switch (state) {
            RiveLoaded(:final controller) => _maybeTint(
              RiveWidget(controller: controller, fit: Fit.contain),
            ),
            RiveFailed() => fallback,
            RiveLoading() => SizedBox(width: size, height: size),
          },
        ),
      ),
    );
  }

  Widget _maybeTint(Widget child) {
    final colour = tint;
    if (colour == null) return child;
    return ColorFiltered(
      colorFilter: ColorFilter.mode(colour, BlendMode.srcIn),
      child: child,
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

/// Static stand-in for an icon artboard when Rive is unavailable (tests) or a
/// decode fails. The Material bridge shares the artboard's name so a broken
/// custom set is visible rather than blank.
class _IconFallback extends StatelessWidget {
  const _IconFallback({
    required this.name,
    required this.size,
    required this.tint,
    this.semanticLabel,
  });

  final String name;
  final double size;
  final Color tint;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    return _artSemantics(
      semanticLabel,
      SizedBox(
        width: size,
        height: size,
        child: Icon(materialIconForArtboard(name), size: size, color: tint),
      ),
    );
  }
}

/// Maps an artboard name to its Material Symbols Outlined counterpart.
///
/// A temporary bridge for the static fallback only: the shipped set is the
/// custom artboards rendered by [SabIconArt]. Material Symbols Outlined sits on
/// the same 24px grid as branding.md's "Iconography", so a fallback still reads
/// as the right glyph. A name Material does not know resolves to
/// `Icons.help_outline` so a wrong bridge is visible rather than blank.
IconData materialIconForArtboard(String artboard) => switch (artboard) {
  'IconHome' => Icons.home_outlined,
  'IconReceipts' => Icons.receipt_long_outlined,
  'IconAccount' => Icons.person_outline_rounded,
  'IconSend' => Icons.send_rounded,
  'IconClose' => Icons.close_rounded,
  'IconChevronRight' => Icons.chevron_right_rounded,
  'IconSearch' => Icons.search_rounded,
  'IconRetry' => Icons.refresh_rounded,
  'IconCopy' => Icons.copy_rounded,
  'IconCheck' => Icons.check_rounded,
  'IconInfo' => Icons.info_outline_rounded,
  'IconOffline' => Icons.wifi_off_outlined,
  'IconHelp' => Icons.help_outline_rounded,
  'IconAdd' => Icons.add_rounded,
  'IconSignOut' => Icons.logout_rounded,
  'IconLanguage' => Icons.translate_rounded,
  'IconStatusPending' => Icons.schedule_outlined,
  'IconStatusSettled' => Icons.check_circle_outline,
  'IconStatusFailed' => Icons.error_outline,
  'IconStatusAwaitingReceipt' => Icons.hourglass_bottom_outlined,
  'IconStatusUnverified' => Icons.gpp_maybe_outlined,
  'IconStatusVerified' => Icons.verified_outlined,
  'IconStatusSuspended' => Icons.block_outlined,
  'IconError' => Icons.error_outline_rounded,
  'IconChannelUssd' => Icons.dialpad_outlined,
  'IconChannelSms' => Icons.sms_outlined,
  'IconChannelWhatsapp' => Icons.chat_outlined,
  'IconPaymentMethod' => Icons.account_balance_wallet_outlined,
  _ => Icons.help_outline_rounded,
};
