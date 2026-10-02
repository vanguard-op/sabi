import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../design_system/icons.dart';
import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';

/// The navigation shell (screens.md): a bottom bar with Home, Receipts, and
/// Account. It wraps only the three tabbed screens; task-first surfaces push
/// above it without the shell.
class NavigationShell extends ConsumerWidget {
  const NavigationShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = ref.watch(sabStringsProvider);
    final colors = SabColorTokens.of(context);
    final index = navigationShell.currentIndex;
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(top: BorderSide(color: colors.border)),
        ),
        child: BottomNavigationBar(
          currentIndex: index,
          onTap: (i) =>
              navigationShell.goBranch(i, initialLocation: i == index),
          items: [
            BottomNavigationBarItem(
              icon: const Icon(SabIcons.home),
              activeIcon: const Icon(SabIcons.homeActive),
              label: strings.homeTitle,
            ),
            BottomNavigationBarItem(
              icon: const Icon(SabIcons.receipts),
              activeIcon: const Icon(SabIcons.receiptsActive),
              label: strings.receiptsTitle,
            ),
            BottomNavigationBarItem(
              icon: const Icon(SabIcons.account),
              activeIcon: const Icon(SabIcons.accountActive),
              label: strings.accountTitle,
            ),
          ],
        ),
      ),
    );
  }
}
