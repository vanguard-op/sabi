import 'package:flutter/material.dart';

/// Semantic icon names used across the client.
///
/// branding.md specifies a custom 24px, 2px-stroke outlined set drawn to the
/// mark's rounded geometry; that set is not in the asset ledger yet. These
/// Material outlined glyphs stand in behind semantic names so swapping in the
/// custom set is a one-file change and no screen names a raw glyph.
abstract final class SabIcons {
  static const IconData home = Icons.home_outlined;
  static const IconData homeActive = Icons.home_rounded;

  static const IconData receipts = Icons.receipt_long_outlined;
  static const IconData receiptsActive = Icons.receipt_long_rounded;

  static const IconData account = Icons.person_outline_rounded;
  static const IconData accountActive = Icons.person_rounded;

  static const IconData send = Icons.send_rounded;
  static const IconData close = Icons.close_rounded;
  static const IconData chevronRight = Icons.chevron_right_rounded;
  static const IconData search = Icons.search_rounded;
  static const IconData retry = Icons.refresh_rounded;
  static const IconData copy = Icons.copy_rounded;
  static const IconData check = Icons.check_rounded;
  static const IconData info = Icons.info_outline_rounded;
  static const IconData offline = Icons.wifi_off_outlined;
  static const IconData help = Icons.help_outline_rounded;

  // Status glyphs — paired with a text label so colour is never the only signal.
  static const IconData statusPending = Icons.schedule_outlined;
  static const IconData statusSettled = Icons.check_circle_outline;
  static const IconData statusFailed = Icons.error_outline;
  static const IconData statusAwaitingReceipt = Icons.hourglass_bottom_outlined;
  static const IconData statusUnverified = Icons.gpp_maybe_outlined;
  static const IconData statusVerified = Icons.verified_outlined;
  static const IconData statusSuspended = Icons.block_outlined;

  // Channel glyphs.
  static const IconData channelUssd = Icons.dialpad_outlined;
  static const IconData channelSms = Icons.sms_outlined;
  static const IconData channelWhatsapp = Icons.chat_outlined;

  static const IconData paymentMethod = Icons.account_balance_wallet_outlined;
  static const IconData add = Icons.add_rounded;
  static const IconData signOut = Icons.logout_rounded;
  static const IconData language = Icons.translate_rounded;
  static const IconData error = Icons.error_outline_rounded;
  static const IconData emptyReceipts = Icons.receipt_long_outlined;
}
