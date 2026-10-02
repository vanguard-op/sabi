import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/money.dart';
import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';
import 'sab_button.dart';
import 'sab_text_field.dart';

/// Bottom sheet for a variable amount (screens.md, "Amount Entry"). Validates
/// against the provider's range and returns the amount in minor units (kobo).
Future<int?> showSabAmountEntrySheet(
  BuildContext context, {
  int? minMinor,
  int? maxMinor,
  String currency = 'NGN',
}) {
  return showModalBottomSheet<int>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: _AmountEntry(
        minMinor: minMinor,
        maxMinor: maxMinor,
        currency: currency,
      ),
    ),
  );
}

class _AmountEntry extends ConsumerStatefulWidget {
  const _AmountEntry({
    this.minMinor,
    this.maxMinor,
    this.currency = SabMoney.defaultCurrency,
  });

  final int? minMinor;
  final int? maxMinor;
  final String currency;

  @override
  ConsumerState<_AmountEntry> createState() => _AmountEntryState();
}

class _AmountEntryState extends ConsumerState<_AmountEntry> {
  final _controller = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final strings = ref.read(sabStringsProvider);
    final parsed = double.tryParse(_controller.text.trim());
    if (parsed == null || parsed <= 0) {
      setState(() => _error = strings.requiredField);
      return;
    }
    final minor = (parsed * 100).round();
    final below = widget.minMinor != null && minor < widget.minMinor!;
    final above = widget.maxMinor != null && minor > widget.maxMinor!;
    if (below || above) {
      setState(() => _error = strings.amountOutOfRange);
      return;
    }
    Navigator.of(context).pop(minor);
  }

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    return Padding(
      padding: const EdgeInsets.all(SabSpacing.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            strings.amountEntryTitle,
            style: SabTypography.h3.copyWith(color: colors.textPrimary),
          ),
          const SizedBox(height: SabSpacing.md),
          SabTextField(
            label: strings.amount,
            hint: strings.amountEntryHint,
            controller: _controller,
            errorText: _error,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            textInputAction: TextInputAction.done,
            autofocus: true,
            onSubmitted: (_) => _submit(),
            suffixIcon: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: SabSpacing.md,
                vertical: SabSpacing.md,
              ),
              child: Text(
                SabMoney.symbolFor(widget.currency),
                style: SabTypography.body.copyWith(color: colors.textSecondary),
              ),
            ),
          ),
          const SizedBox(height: SabSpacing.md),
          SabButton(
            label: strings.continueLabel,
            expand: true,
            onPressed: _submit,
          ),
        ],
      ),
    );
  }
}
