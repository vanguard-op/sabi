import 'package:flutter/material.dart';

import '../design_system/icons.dart';
import '../design_system/tokens.dart';

/// Confirms a stored receipt or token (screens.md, "Success Toast"). It never
/// carries the only success signal: the surface also shows a Status Pill.
void showSabSuccessToast(BuildContext context, String message) {
  final colors = SabColorTokens.of(context);
  final messenger = ScaffoldMessenger.of(context);
  messenger
    ..clearSnackBars()
    ..showSnackBar(
      SnackBar(
        duration: SabMotion.emphasized * 6,
        content: Row(
          children: [
            SabIconView(
              SabIcons.check,
              size: SabSizes.iconMd,
              color: colors.success500,
            ),
            const SizedBox(width: SabSpacing.sm),
            Expanded(child: Text(message)),
          ],
        ),
      ),
    );
}
