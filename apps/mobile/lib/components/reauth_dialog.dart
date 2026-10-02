import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';
import 'sab_button.dart';

/// The re-authorisation overlay (screens.md, "Re-authorisation"). It blocks the
/// surface until re-authenticated and the caller preserves screen state. Returns
/// true once re-authentication succeeds.
Future<bool> showSabReauthDialog(
  BuildContext context, {
  required Future<bool> Function() onReauth,
}) async {
  final result = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (context) => _ReauthDialog(onReauth: onReauth),
  );
  return result ?? false;
}

class _ReauthDialog extends ConsumerStatefulWidget {
  const _ReauthDialog({required this.onReauth});

  final Future<bool> Function() onReauth;

  @override
  ConsumerState<_ReauthDialog> createState() => _ReauthDialogState();
}

class _ReauthDialogState extends ConsumerState<_ReauthDialog> {
  bool _busy = false;
  bool _failed = false;

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _failed = false;
    });
    final ok = await widget.onReauth();
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop(true);
    } else {
      setState(() {
        _busy = false;
        _failed = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    return AlertDialog(
      title: Text(strings.reauthTitle),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(strings.reauthBody),
          if (_failed) ...[
            const SizedBox(height: SabSpacing.sm),
            Text(
              strings.passkeyFailed,
              style: SabTypography.bodySmall.copyWith(color: colors.error500),
            ),
          ],
        ],
      ),
      actions: [
        SabButton(
          label: strings.reauthAction,
          loading: _busy,
          onPressed: _busy ? null : _submit,
        ),
      ],
    );
  }
}
