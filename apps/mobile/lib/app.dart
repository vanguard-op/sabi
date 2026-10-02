import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'design_system/theme.dart';
import 'router/app_router.dart';

/// The Sabi client root. Both themes come from the token layer; the compose
/// model means a screen renders in either mode without a second stylesheet.
class SabApp extends ConsumerWidget {
  const SabApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'Sabi',
      debugShowCheckedModeBanner: false,
      theme: buildSabTheme(Brightness.light),
      darkTheme: buildSabTheme(Brightness.dark),
      themeMode: ThemeMode.system,
      routerConfig: router,
      supportedLocales: const [Locale('en', 'NG'), Locale('pcm')],
      locale: const Locale('en', 'NG'),
    );
  }
}
