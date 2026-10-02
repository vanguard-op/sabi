import 'package:flutter/material.dart';

import 'sab_art.dart';
import 'tokens.dart';

/// The client's custom 24px outlined icon set (ASSETS.md A-009; branding.md,
/// "Iconography"). Each semantic name resolves to a Rive artboard in the single
/// runtime file `assets/sabi.riv`, loaded by name (D-016).
///
/// Screens never name a raw glyph or a Material icon; they name a role here, so
/// the whole set is repointed from one file. The artboards are authored
/// one-colour in `text-secondary` and the client tints them per state.
///
/// The artboards are drawn on a 24-unit grid with a 2px stroke; [SabIcon]
/// scales the 24px artboard to the [size] it is given.
enum SabIcon {
  home('IconHome'),
  receipts('IconReceipts'),
  account('IconAccount'),
  send('IconSend'),
  close('IconClose'),
  chevronRight('IconChevronRight'),
  search('IconSearch'),
  retry('IconRetry'),
  copy('IconCopy'),
  check('IconCheck'),
  info('IconInfo'),
  offline('IconOffline'),
  help('IconHelp'),
  add('IconAdd'),
  signOut('IconSignOut'),
  language('IconLanguage'),
  statusPending('IconStatusPending'),
  statusSettled('IconStatusSettled'),
  statusFailed('IconStatusFailed'),
  statusAwaitingReceipt('IconStatusAwaitingReceipt'),
  statusUnverified('IconStatusUnverified'),
  statusVerified('IconStatusVerified'),
  statusSuspended('IconStatusSuspended'),
  error('IconError'),
  channelUssd('IconChannelUssd'),
  channelSms('IconChannelSms'),
  channelWhatsapp('IconChannelWhatsapp'),
  paymentMethod('IconPaymentMethod');

  const SabIcon(this.artboard);

  /// The Rive artboard name in `assets/sabi.riv`.
  final String artboard;
}

/// Semantic icon names used across the client.
///
/// Kept as the single naming surface so a call site reads `SabIcons.home`
/// rather than reaching through [SabIcon]. The navigation shell uses one
/// artboard per tab tinted by the bar, so there is no separate active glyph.
abstract final class SabIcons {
  static const SabIcon home = SabIcon.home;
  static const SabIcon receipts = SabIcon.receipts;
  static const SabIcon account = SabIcon.account;

  static const SabIcon send = SabIcon.send;
  static const SabIcon close = SabIcon.close;
  static const SabIcon chevronRight = SabIcon.chevronRight;
  static const SabIcon search = SabIcon.search;
  static const SabIcon retry = SabIcon.retry;
  static const SabIcon copy = SabIcon.copy;
  static const SabIcon check = SabIcon.check;
  static const SabIcon info = SabIcon.info;
  static const SabIcon offline = SabIcon.offline;
  static const SabIcon help = SabIcon.help;
  static const SabIcon add = SabIcon.add;
  static const SabIcon signOut = SabIcon.signOut;
  static const SabIcon language = SabIcon.language;
  static const SabIcon paymentMethod = SabIcon.paymentMethod;

  // Status glyphs — paired with a text label so colour is never the only signal.
  static const SabIcon statusPending = SabIcon.statusPending;
  static const SabIcon statusSettled = SabIcon.statusSettled;
  static const SabIcon statusFailed = SabIcon.statusFailed;
  static const SabIcon statusAwaitingReceipt = SabIcon.statusAwaitingReceipt;
  static const SabIcon statusUnverified = SabIcon.statusUnverified;
  static const SabIcon statusVerified = SabIcon.statusVerified;
  static const SabIcon statusSuspended = SabIcon.statusSuspended;

  // Channel glyphs.
  static const SabIcon channelUssd = SabIcon.channelUssd;
  static const SabIcon channelSms = SabIcon.channelSms;
  static const SabIcon channelWhatsapp = SabIcon.channelWhatsapp;

  static const SabIcon error = SabIcon.error;
}

/// A colour- and size-aware icon using the custom Rive artboards (ASSETS.md
/// A-009), so screens never name a raw glyph.
///
/// In production it renders the 24px artboard from the single runtime file and
/// tints it with [color] (defaulting to `text-secondary`). In static mode
/// (tests) it falls back to the Material bridge so no Rive decode runs.
class SabIconView extends StatelessWidget {
  const SabIconView(
    this.icon, {
    super.key,
    this.size = 24,
    this.color,
    this.semanticLabel,
  });

  final SabIcon icon;
  final double size;
  final Color? color;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final tint = color ?? SabColorTokens.of(context).textSecondary;
    return SabIconArt(
      artboardName: icon.artboard,
      size: size,
      tint: tint,
      semanticLabel: semanticLabel,
    );
  }
}
