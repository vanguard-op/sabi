import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';
import '../models/service_summary.dart';
import 'service_result_row.dart';

/// Bottom sheet listing candidate collecting bodies when a request matches more
/// than one (screens.md, "Provider Picker"). Blocks until a choice is made and
/// returns the chosen service, or null if dismissed.
Future<ServiceSummary?> showSabProviderPickerSheet(
  BuildContext context, {
  required List<ServiceSummary> candidates,
}) {
  return showModalBottomSheet<ServiceSummary>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) => _ProviderPicker(candidates: candidates),
  );
}

class _ProviderPicker extends ConsumerWidget {
  const _ProviderPicker({required this.candidates});

  final List<ServiceSummary> candidates;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          SabSpacing.lg,
          0,
          SabSpacing.lg,
          SabSpacing.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              strings.providerPickerTitle,
              style: SabTypography.h3.copyWith(color: colors.textPrimary),
            ),
            const SizedBox(height: SabSpacing.md),
            Flexible(
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: candidates.length,
                separatorBuilder: (_, _) =>
                    const SizedBox(height: SabSpacing.sm),
                itemBuilder: (context, index) {
                  final service = candidates[index];
                  return ServiceResultRow(
                    service: service,
                    onSelect: () => Navigator.of(context).pop(service),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
