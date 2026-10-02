import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:rive/rive.dart';

import 'app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Native Rive runtime, so the brand mark and custom icon set are ready before
  // the first frame rather than initialising lazily during it (NFR-001).
  await RiveNative.init();
  // Date formatting for the launch locales, so dates go through locale APIs.
  await initializeDateFormatting('en_NG');
  runApp(const ProviderScope(child: SabApp()));
}
