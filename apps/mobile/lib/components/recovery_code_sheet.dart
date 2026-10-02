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
              // The whole row is the 44px touch target; the checkbox itself is a
              // row child centred against the label so the two stay aligned at
              // any text scale without a per-call-site vertical nudge. The
              // label grows first (down) as the checkbox is smaller.
              Semantics(
                label: strings.recoveryAcknowledge,
                checked: _acknowledged,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    minHeight: SabSizes.minTouchTarget,
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // `radius-sm` (4px) is the documented checkbox radius; the
                      // default M3 shape is 2px. `shrinkWrap` keeps the visual
                      // square butting the label, while the row above still
                      // carries the 44px minimum touch target.
                      Checkbox(
                        value: _acknowledged,
                        onChanged: (value) =>
                            setState(() => _acknowledged = value ?? false),
                        isError: false,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(SabRadii.sm),
                        ),
                        side: BorderSide(color: colors.border),
                        activeColor: colors.primary500,
                        checkColor: colors.onPrimary,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                      const SizedBox(width: SabSpacing.sm),
                      Expanded(
                        child: Text(
                          strings.recoveryAcknowledge,
                          style: SabTypography.body.copyWith(
                            color: colors.textPrimary,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
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
