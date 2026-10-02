import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../design_system/icons.dart';
import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';
import 'sab_button.dart';
import 'success_toast.dart';

/// The one-time recovery code sheet (screens.md, Welcome overlay). It blocks
/// until acknowledged, is shown once, and is not linkable.
Future<bool> showSabRecoveryCodeSheet(
  BuildContext context, {
  required String code,
}) async {
  final result = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    isDismissible: false,
    enableDrag: false,
    builder: (context) => _RecoveryCodeSheet(code: code),
  );
  return result ?? false;
}

class _RecoveryCodeSheet extends ConsumerStatefulWidget {
  const _RecoveryCodeSheet({required this.code});

  final String code;

  @override
  ConsumerState<_RecoveryCodeSheet> createState() => _RecoveryCodeSheetState();
}

class _RecoveryCodeSheetState extends ConsumerState<_RecoveryCodeSheet> {
  bool _acknowledged = false;

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    if (!mounted) return;
    showSabSuccessToast(context, ref.read(sabStringsProvider).recoveryCopied);
  }

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    return PopScope(
      canPop: false,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(SabSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                strings.recoveryTitle,
                style: SabTypography.h2.copyWith(color: colors.textPrimary),
              ),
              const SizedBox(height: SabSpacing.sm),
              Text(
                strings.recoveryBody,
                style: SabTypography.body.copyWith(color: colors.textSecondary),
              ),
              const SizedBox(height: SabSpacing.lg),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(SabSpacing.md),
                decoration: BoxDecoration(
                  color: colors.primary100,
                  borderRadius: BorderRadius.circular(SabRadii.md),
                  border: Border.all(color: colors.primary300),
                ),
                child: SelectableText(
                  widget.code,
                  textAlign: TextAlign.center,
                  style: SabTypography.monoCode.copyWith(
                    color: colors.primary900,
                  ),
                ),
              ),
              const SizedBox(height: SabSpacing.sm),
              Align(
                alignment: Alignment.centerRight,
                child: SabButton(
                  label: strings.recoveryCopy,
                  variant: SabButtonVariant.ghost,
                  icon: SabIcons.copy,
                  onPressed: _copy,
                ),
              ),
              const SizedBox(height: SabSpacing.sm),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: SabSizes.minTouchTarget,
                    height: SabSizes.minTouchTarget,
                    child: Checkbox(
                      value: _acknowledged,
                      onChanged: (value) =>
                          setState(() => _acknowledged = value ?? false),
                    ),
                  ),
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.only(top: SabSpacing.md),
                      child: Text(
                        strings.recoveryAcknowledge,
                        style: SabTypography.body.copyWith(
                          color: colors.textPrimary,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: SabSpacing.sm),
              Text(
                strings.recoveryWarning,
                style: SabTypography.caption.copyWith(color: colors.error500),
              ),
              const SizedBox(height: SabSpacing.lg),
              SabButton(
                label: strings.continueLabel,
                expand: true,
                onPressed: _acknowledged
                    ? () => Navigator.of(context).pop(true)
                    : null,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
