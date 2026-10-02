import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Date formatting for the launch locales, so dates go through locale APIs.
  await initializeDateFormatting('en_NG');
  runApp(const ProviderScope(child: SabApp()));
}
