import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'data/providers.dart';
import 'design_system/theme.dart';
import 'router/app_router.dart';

/// The Sabi client root. Both themes come from the token layer; the compose
/// model means a screen renders in either mode without a second stylesheet.
class SabApp extends ConsumerWidget {
  const SabApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    // Kick off the launch check: it restores the persisted session cookie and
    // verifies it, resolving the session store the router listens to. Watching
    // it here means it runs once for the app's lifetime.
    ref.watch(sessionBootstrapProvider);
    return MaterialApp.router(
      title: 'Sabi',
      debugShowCheckedModeBanner: false,
      theme: buildSabTheme(Brightness.light),
      darkTheme: buildSabTheme(Brightness.dark),
      themeMode: ThemeMode.system,
      // Surfaces without an app bar (Welcome, Sign In) still draw the token
      // status and navigation bar style; a screen with an app bar is covered
      // by AppBarTheme.systemOverlayStyle.
      builder: (context, child) =>
          SabSystemBars(child: child ?? const SizedBox.shrink()),
      routerConfig: router,
      supportedLocales: const [Locale('en', 'NG'), Locale('pcm')],
      locale: const Locale('en', 'NG'),
    );
  }
}
