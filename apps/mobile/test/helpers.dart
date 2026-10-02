import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:sabi_mobile/app.dart';
import 'package:sabi_mobile/design_system/sab_art.dart';
import 'package:sabi_mobile/design_system/theme.dart';

bool _intlReady = false;

Future<void> _ensureIntl() async {
  if (_intlReady) return;
  await initializeDateFormatting('en_NG');
  _intlReady = true;
}

/// Pumps a screen with the token theme and static art (no Rive decode in unit
/// tests). Overrides replace the mock repositories or the session.
Future<void> pumpSab(
  WidgetTester tester,
  Widget child, {
  List<Override> overrides = const [],
  Brightness brightness = Brightness.light,
}) async {
  await _ensureIntl();
  await tester.pumpWidget(
    SabArtMode(
      staticOnly: true,
      child: ProviderScope(
        overrides: overrides,
        child: MaterialApp(theme: buildSabTheme(brightness), home: child),
      ),
    ),
  );
}

/// Pumps the whole app, router included, with static art.
Future<void> pumpSabApp(
  WidgetTester tester, {
  List<Override> overrides = const [],
}) async {
  await _ensureIntl();
  await tester.pumpWidget(
    SabArtMode(
      staticOnly: true,
      child: ProviderScope(overrides: overrides, child: const SabApp()),
    ),
  );
}

/// Finds the Riverpod container behind the pumped widget tree.
ProviderContainer containerOf(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(MaterialApp)));
