import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';
import '../models/composed_surface.dart';
import '../models/receipt_summary.dart';
import '../models/service_summary.dart';
import 'confirmation_summary.dart';
import 'receipt_card.dart';
import 'service_result_row.dart';
import 'status_pill.dart';

/// The components the client exposes to the agent (FEAT-011). A message that
/// names anything outside this set is refused and the surface falls back to a
/// plain form, so the task stays completable.
abstract final class SabComponentCatalogue {
  static const Set<String> types = {
    'text',
    'confirmationSummary',
    'serviceResultRow',
    'receiptCard',
    'statusPill',
    'amountEntry',
  };
}

/// Renders an agent-composed surface from the declarative stream (CONTRACTS.md
/// C-012). The client owns the styling; the agent only names catalogue
/// components. Partial data renders placeholders, and a surface that fails
/// validation renders the text-and-form fallback instead of a raw message.
class ComposedTaskSurface extends ConsumerWidget {
  const ComposedTaskSurface({
    super.key,
    required this.surface,
    this.onServiceSelected,
    this.onFallbackAction,
    this.fallbackPrompt,
  });

  final ComposedSurface surface;
  final ValueChanged<ServiceSummary>? onServiceSelected;
  final VoidCallback? onFallbackAction;
  final String? fallbackPrompt;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final renderable =
        surface.task != null &&
        surface.components.isNotEmpty &&
        surface.components.every(
          (c) => SabComponentCatalogue.types.contains(c.type),
        );
    if (!renderable) {
      return _FallbackForm(
        prompt:
            fallbackPrompt ?? ref.watch(sabStringsProvider).unknownComponent,
        onSubmit: onFallbackAction,
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final component in surface.components) ...[
          _buildComponent(context, ref, component),
          const SizedBox(height: SabSpacing.md),
        ],
      ],
    );
  }

  Widget _buildComponent(
    BuildContext context,
    WidgetRef ref,
    SurfaceComponent component,
  ) {
    final data = {...surface.data, ...component.data};
    switch (component.type) {
      case 'text':
        return Text(
          (data['text'] ?? '').toString(),
          style: SabTypography.body.copyWith(
            color: SabColorTokens.of(context).textPrimary,
          ),
        );
      case 'confirmationSummary':
        return ConfirmationSummary(
          amount: (data['amount'] as num?)?.toInt() ?? 0,
          currency: (data['currency'] ?? 'NGN').toString(),
          payee: (data['payee'] ?? '').toString(),
          charges: (data['charges'] as num?)?.toInt(),
          reference: data['reference']?.toString(),
        );
      case 'serviceResultRow':
        final raw = data['service'];
        final service = raw is Map
            ? ServiceSummary.fromJson(raw.cast<String, dynamic>())
            : ServiceSummary.fromJson(data);
        return ServiceResultRow(
          service: service,
          onSelect: () => onServiceSelected?.call(service),
        );
      case 'receiptCard':
        final raw = data['receipt'];
        final receipt = raw is Map
            ? ReceiptSummary.fromJson(raw.cast<String, dynamic>())
            : ReceiptSummary.fromJson(data);
        return ReceiptCard(receipt: receipt, onTap: onFallbackAction);
      case 'statusPill':
        return Align(
          alignment: Alignment.centerLeft,
          child: StatusPill(status: _statusFrom(data['status'])),
        );
      case 'amountEntry':
        return SabFallbackButton(
          label: ref.watch(sabStringsProvider).amountEntryTitle,
          onPressed: onFallbackAction,
        );
      default:
        // Unreachable: the catalogue check above filters unknown types.
        return const SizedBox.shrink();
    }
  }

  SabStatus _statusFrom(Object? raw) => switch (raw?.toString()) {
    'settled' => SabStatus.settled,
    'failed' => SabStatus.failed,
    'awaiting_receipt' || 'awaitingReceipt' => SabStatus.awaitingReceipt,
    _ => SabStatus.pending,
  };
}

/// A simple call to action used inside composed surfaces. Kept local so the
/// surface does not depend on screen-level button wiring.
class SabFallbackButton extends StatelessWidget {
  const SabFallbackButton({super.key, required this.label, this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    return Align(
      alignment: Alignment.centerLeft,
      child: OutlinedButton(
        onPressed: onPressed,
        child: Text(
          label,
          style: SabTypography.body.copyWith(
            color: colors.primary500,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}

class _FallbackForm extends ConsumerStatefulWidget {
  const _FallbackForm({required this.prompt, this.onSubmit});

  final String prompt;
  final VoidCallback? onSubmit;

  @override
  ConsumerState<_FallbackForm> createState() => _FallbackFormState();
}

class _FallbackFormState extends ConsumerState<_FallbackForm> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    return Container(
      padding: const EdgeInsets.all(SabSpacing.md),
      decoration: BoxDecoration(
        color: colors.surfaceSecondary,
        borderRadius: BorderRadius.circular(SabRadii.md),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  widget.prompt,
                  style: SabTypography.bodySmall.copyWith(
                    color: colors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: SabSpacing.md),
          TextField(
            controller: _controller,
            decoration: InputDecoration(hintText: strings.composerHint),
          ),
          const SizedBox(height: SabSpacing.md),
          SabFallbackButton(
            label: strings.continueLabel,
            onPressed: widget.onSubmit,
          ),
        ],
      ),
    );
  }
}
