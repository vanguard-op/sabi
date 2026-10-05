import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:genui/genui.dart';
import 'package:json_schema_builder/json_schema_builder.dart';

import '../components/confirmation_summary.dart';
import '../components/receipt_card.dart';
import '../components/service_result_row.dart';
import '../components/status_pill.dart';
import '../design_system/tokens.dart';
import '../l10n/sab_strings.dart';
import '../models/receipt_summary.dart';
import '../models/service_summary.dart';
import 'sabi_catalog_document.dart';

/// The Sabi A2UI catalog (FEAT-011, C-012 revision 2).
///
/// The catalog is the single source of truth the agent composes against and
/// both sides validate against (A2UI "Catalogs"). It is a JSON Schema
/// conforming to A2UI's Catalog schema, identified by [sabiCatalogId], which is
/// both the A2UI `catalogId` and the document `$id` (A2UI requires both to be
/// the same URI). The client advertises it through `supportedCatalogIds`; the
/// agent names it on `createSurface`; and the client validates every incoming
/// message against it before rendering (client-side phase of A2UI's two-phase
/// validation).
///
/// Only the composed task surfaces are in the catalog. The shell (composer,
/// navigation, static chrome, fixed buttons and labels) is prewritten client
/// code and is never composed, so it is deliberately absent.
abstract final class SabiCatalog {
  SabiCatalog._();

  /// The catalog URI. Per A2UI, `catalogId` and the schema document's `$id`
  /// are the same URI; the major version is carried in the path (v1), and the
  /// catalog evolves additively within it (A2UI "Catalog Naming & Versioning").
  ///
  /// The single authored definition lives in `sabi_catalog_document.dart`; this
  /// is a `const` alias so call sites can keep using it in constant contexts.
  static const String catalogId = sabiCatalogId;

  /// The task surfaces the catalog exposes. Each maps to exactly one component
  /// the client renders, so an unknown component is anything outside this set.
  static const SabComponentName confirmationSummary = SabComponentName(
    'ConfirmationSummary',
  );
  static const SabComponentName amountEntry = SabComponentName('AmountEntry');
  static const SabComponentName providerPicker = SabComponentName(
    'ProviderPicker',
  );
  static const SabComponentName serviceResultRow = SabComponentName(
    'ServiceResultRow',
  );
  static const SabComponentName receiptCard = SabComponentName('ReceiptCard');
  static const SabComponentName statusPill = SabComponentName('StatusPill');
  static const SabComponentName verification = SabComponentName('Verification');
  static const SabComponentName recovery = SabComponentName('Recovery');

  /// The canonical component names, in catalog order, read from the single
  /// authored document so the set can never drift from it.
  static final List<String> componentNames = (document()['components'] as Map)
      .keys
      .cast<String>()
      .toList(growable: false);

  /// Whether [name] is a component the catalog defines. Used by the client-side
  /// validation to refuse an unknown component and fall back for the task.
  static bool defines(String name) => componentNames.contains(name);

  /// The published catalog document: a standalone JSON Schema whose `$id` is
  /// [catalogId] and whose `components` mirror the renderer's items. A2UI
  /// catalogs must be freestanding (no external `$ref`s), so this is the exact
  /// document the agent composes against and the client validates with.
  ///
  /// The document is authored once in `sabi_catalog_document.dart` and generated
  /// into `services/ai/core/catalogs/sabi_a2ui_v1.json` at build time, so there
  /// is exactly one catalog to edit.
  static Map<String, Object?> document() => buildSabiCatalogDocument();

  /// The catalog document serialised for the wire or for inspection.
  static String documentJson() => jsonEncode(document());
}

/// A typed catalog component name, so a call site cannot misspell one.
@immutable
class SabComponentName {
  const SabComponentName(this.value);

  final String value;

  @override
  bool operator ==(Object other) =>
      other is SabComponentName && other.value == value;

  @override
  int get hashCode => value.hashCode;

  @override
  String toString() => value;
}

/// Builds the GenUI [Catalog] the renderer uses (FEAT-011). The component
/// schemas mirror [SabiCatalog.document] exactly; the widget builders render
/// the Sabi components with design tokens, so the agent can only request the
/// surface and the client owns styling and security.
final Catalog sabiCatalog = Catalog(
  [
    _confirmationSummaryItem,
    _amountEntryItem,
    _providerPickerItem,
    _serviceResultRowItem,
    _receiptCardItem,
    _statusPillItem,
    _verificationItem,
    _recoveryItem,
  ],
  catalogId: SabiCatalog.catalogId,
  systemPromptFragments: const [
    'Use ConfirmationSummary for a resolved payment awaiting authorisation, '
        'AmountEntry when the amount is not yet known, ProviderPicker when '
        'several collecting bodies match, ServiceResultRow for a single '
        'discovery result, ReceiptCard for a resolved record or receipt, '
        'StatusPill for a payment state, Verification for an identity task, '
        'and Recovery for a failed-payment or case task.',
    'One component in the updateComponents message must have id "root"; a '
        'surface with no root renders nothing.',
  ],
);

/// The `supportedCatalogIds` the client advertises in the A2UI negotiation.
List<String> get sabiSupportedCatalogIds =>
    A2UiClientCapabilities.fromCatalogs([sabiCatalog]).supportedCatalogIds;

/// The action names the catalog's components dispatch back to the host (A2UI
/// actions). The host routes them; the component only names the intent.
abstract final class SabiActions {
  SabiActions._();

  /// A discovery result was chosen: context carries `serviceId`.
  static const String selectService = 'sabi.selectService';

  /// A composed record was opened: context carries `recordRef`.
  static const String openRecord = 'sabi.openRecord';

  /// The identity-verification next step was chosen.
  static const String openVerification = 'sabi.openVerification';

  /// The recovery (case) next step was chosen: context carries `recordRef`.
  static const String openCase = 'sabi.openCase';
}

// --- Catalog items --------------------------------------------------------
// Each item mirrors one component in [SabiCatalog.document]. A builder receives
// the flat v0.9 component properties on `itemContext.data`; bound values are
// resolved through the data model, so a `{path: ...}` binding from the agent
// works (A2UI data binding).

/// A scalar that is either [type] or null, matching the published document's
/// `['<type>', 'null']` for an optional field. The document is the contract the
/// agent composes against, so an explicit null it permits must validate here
/// too; a non-nullable runtime type refused it and silently fell back.
Schema _nullable(JsonType type) => S.combined(type: [type, JsonType.nil]);

final CatalogItem _confirmationSummaryItem = CatalogItem(
  name: SabiCatalog.confirmationSummary.value,
  dataSchema: S.object(
    properties: {
      'amount': S.integer(),
      'currency': S.string(),
      'payee': S.string(),
      'charges': _nullable(JsonType.int),
      'reference': _nullable(JsonType.string),
    },
    required: ['amount', 'payee'],
  ),
  widgetBuilder: _confirmationSummary,
);

final CatalogItem _amountEntryItem = CatalogItem(
  name: SabiCatalog.amountEntry.value,
  dataSchema: S.object(
    properties: {
      'currency': S.string(),
      'minimum': _nullable(JsonType.int),
      'maximum': _nullable(JsonType.int),
      'prompt': _nullable(JsonType.string),
    },
  ),
  widgetBuilder: _amountEntry,
);

/// The `ServiceResultRow` data shape, authored once and shared by the standalone
/// row item and by each entry of [SabiCatalog.providerPicker]'s `services`
/// array. The published document points `ProviderPicker.services.items` at
/// `#/components/ServiceResultRow`, so an entry must carry the same declared
/// properties and the same required fields; without them the client-side
/// validation accepted an empty `{}` entry and the picker drew a blank row.
final Schema _serviceResultRowSchema = S.object(
  properties: {
    'serviceId': S.string(),
    'name': S.string(),
    'collectingBody': S.string(),
    'category': S.string(),
    'knownAmount': _nullable(JsonType.int),
    'currency': S.string(),
    'status': S.string(),
    'confidence': S.number(),
  },
  required: ['serviceId', 'collectingBody', 'category'],
);

final CatalogItem _providerPickerItem = CatalogItem(
  name: SabiCatalog.providerPicker.value,
  dataSchema: S.object(
    properties: {'services': S.list(items: _serviceResultRowSchema)},
    required: ['services'],
  ),
  widgetBuilder: _providerPicker,
);

final CatalogItem _serviceResultRowItem = CatalogItem(
  name: SabiCatalog.serviceResultRow.value,
  dataSchema: _serviceResultRowSchema,
  widgetBuilder: _serviceResultRow,
);

final CatalogItem _receiptCardItem = CatalogItem(
  name: SabiCatalog.receiptCard.value,
  dataSchema: S.object(
    properties: {
      'receiptId': S.string(),
      'reference': S.string(),
      'payee': S.string(),
      'amount': S.integer(),
      'currency': S.string(),
      'issuedAt': S.string(),
      'kind': S.string(),
      'status': S.string(),
    },
    required: ['reference', 'payee', 'amount'],
  ),
  widgetBuilder: _receiptCard,
);

final CatalogItem _statusPillItem = CatalogItem(
  name: SabiCatalog.statusPill.value,
  dataSchema: S.object(
    properties: {'status': S.string(), 'label': _nullable(JsonType.string)},
    required: ['status'],
  ),
  widgetBuilder: _statusPill,
);

final CatalogItem _verificationItem = CatalogItem(
  name: SabiCatalog.verification.value,
  dataSchema: S.object(
    properties: {
      'title': S.string(),
      'body': _nullable(JsonType.string),
      'actionLabel': _nullable(JsonType.string),
    },
    required: ['title'],
  ),
  widgetBuilder: _verification,
);

final CatalogItem _recoveryItem = CatalogItem(
  name: SabiCatalog.recovery.value,
  dataSchema: S.object(
    properties: {
      'title': S.string(),
      'body': _nullable(JsonType.string),
      'status': _nullable(JsonType.string),
      'actionLabel': _nullable(JsonType.string),
    },
    required: ['title'],
  ),
  widgetBuilder: _recovery,
);

Widget _confirmationSummary(CatalogItemContext ctx) {
  final data = _props(ctx);
  return BoundConfirmationSummary(data: data, dataContext: ctx.dataContext);
}

Widget _amountEntry(CatalogItemContext ctx) {
  final data = _props(ctx);
  return BoundAmountEntry(data: data, dataContext: ctx.dataContext);
}

Widget _providerPicker(CatalogItemContext ctx) {
  final data = _props(ctx);
  final raw = data['services'];
  final services = (raw is List ? raw : const [])
      .whereType<Map>()
      .map((e) => ServiceSummary.fromJson(e.cast<String, dynamic>()))
      .toList(growable: false);
  return Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final service in services) ...[
        ServiceResultRow(
          service: service,
          onSelect: () => ctx.dispatchEvent(
            UserActionEvent(
              name: SabiActions.selectService,
              sourceComponentId: ctx.id,
              context: {'serviceId': service.serviceId},
            ),
          ),
        ),
        const SizedBox(height: SabSpacing.sm),
      ],
    ],
  );
}

Widget _serviceResultRow(CatalogItemContext ctx) {
  final data = _props(ctx);
  final raw = data['service'];
  final service = raw is Map
      ? ServiceSummary.fromJson(raw.cast<String, dynamic>())
      : ServiceSummary.fromJson(data);
  return ServiceResultRow(
    service: service,
    onSelect: () => ctx.dispatchEvent(
      UserActionEvent(
        name: SabiActions.selectService,
        sourceComponentId: ctx.id,
        context: {'serviceId': service.serviceId},
      ),
    ),
  );
}

Widget _receiptCard(CatalogItemContext ctx) {
  final data = _props(ctx);
  final raw = data['receipt'];
  final source = raw is Map ? raw.cast<String, dynamic>() : data;
  // The catalog names the record's own identifier `receiptId` so it does not
  // collide with the A2UI component `id`; map it to the display shape.
  final receipt = ReceiptSummary.fromJson({
    ...source,
    'id': source['receiptId'] ?? source['id'],
  });
  return ReceiptCard(
    receipt: receipt,
    onTap: () => ctx.dispatchEvent(
      UserActionEvent(
        name: SabiActions.openRecord,
        sourceComponentId: ctx.id,
        context: {'recordRef': receipt.id},
      ),
    ),
  );
}

Widget _statusPill(CatalogItemContext ctx) {
  final data = _props(ctx);
  return Align(
    alignment: Alignment.centerLeft,
    child: StatusPill(
      status: _statusFrom(data['status']),
      label: data['label']?.toString(),
    ),
  );
}

Widget _verification(CatalogItemContext ctx) {
  final data = _props(ctx);
  return _TaskCard(
    title: data['title']?.toString() ?? '',
    body: data['body']?.toString(),
    actionKind: 'verification',
    onAction: () => ctx.dispatchEvent(
      UserActionEvent(
        name: SabiActions.openVerification,
        sourceComponentId: ctx.id,
      ),
    ),
  );
}

Widget _recovery(CatalogItemContext ctx) {
  final data = _props(ctx);
  return _TaskCard(
    title: data['title']?.toString() ?? '',
    body: data['body']?.toString(),
    actionKind: 'recovery',
    status: data['status']?.toString(),
    onAction: () => ctx.dispatchEvent(
      UserActionEvent(name: SabiActions.openCase, sourceComponentId: ctx.id),
    ),
  );
}

SabStatus _statusFrom(Object? raw) => switch (raw?.toString()) {
  'settled' => SabStatus.settled,
  'failed' => SabStatus.failed,
  'awaiting_receipt' || 'awaitingReceipt' => SabStatus.awaitingReceipt,
  'unverified' => SabStatus.unverified,
  'verified' => SabStatus.verified,
  'suspended' => SabStatus.suspended,
  _ => SabStatus.pending,
};

Map<String, Object?> _props(CatalogItemContext ctx) =>
    (ctx.data as Map).cast<String, Object?>();

/// The confirmation summary, resolving the amount/currency/payee/charges/
/// reference bindings from the data model.
class BoundConfirmationSummary extends StatelessWidget {
  const BoundConfirmationSummary({
    super.key,
    required this.data,
    required this.dataContext,
  });

  final Map<String, Object?> data;
  final DataContext dataContext;

  @override
  Widget build(BuildContext context) {
    return _BoundNumbers(
      dataContext: dataContext,
      amount: data['amount'],
      charges: data['charges'],
      builder: (amount, charges) => BoundString(
        dataContext: dataContext,
        value: data['currency'] ?? 'NGN',
        builder: (context, currency) => BoundString(
          dataContext: dataContext,
          value: data['payee'] ?? '',
          builder: (context, payee) => BoundString(
            dataContext: dataContext,
            value: data['reference'],
            builder: (context, reference) => ConfirmationSummary(
              amount: amount ?? 0,
              currency: currency ?? 'NGN',
              payee: payee ?? '',
              charges: charges,
              reference: reference,
            ),
          ),
        ),
      ),
    );
  }
}

/// The amount entry: an inline field for a variable amount, so the task stays
/// in the conversation. The agent supplies the range; the client owns the
/// field, its validation, and the amount in minor units, exactly as the
/// amount-entry sheet does.
class BoundAmountEntry extends StatelessWidget {
  const BoundAmountEntry({
    super.key,
    required this.data,
    required this.dataContext,
  });

  final Map<String, Object?> data;
  final DataContext dataContext;

  @override
  Widget build(BuildContext context) {
    return _BoundNumbers(
      dataContext: dataContext,
      amount: data['minimum'],
      charges: data['maximum'],
      builder: (minimum, maximum) => _AmountEntryField(
        minimum: minimum,
        maximum: maximum,
        prompt: data['prompt']?.toString(),
      ),
    );
  }
}

/// An inline amount field for the composed surface. Validates against the
/// provider's range and reports the amount in minor units (kobo), mirroring
/// the amount-entry bottom sheet.
class _AmountEntryField extends StatefulWidget {
  const _AmountEntryField({
    required this.minimum,
    required this.maximum,
    this.prompt,
  });

  final int? minimum;
  final int? maximum;
  final String? prompt;

  @override
  State<_AmountEntryField> createState() => _AmountEntryFieldState();
}

class _AmountEntryFieldState extends State<_AmountEntryField> {
  final _controller = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final strings = SabStrings.english;
    final parsed = double.tryParse(_controller.text.trim());
    if (parsed == null || parsed <= 0) {
      setState(() => _error = strings.requiredField);
      return;
    }
    final minor = (parsed * 100).round();
    final below = widget.minimum != null && minor < widget.minimum!;
    final above = widget.maximum != null && minor > widget.maximum!;
    setState(() => _error = (below || above) ? strings.amountOutOfRange : null);
  }

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final strings = SabStrings.english;
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
          Text(
            widget.prompt ?? strings.amountEntryTitle,
            style: SabTypography.body.copyWith(
              color: colors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: SabSpacing.sm),
          TextField(
            controller: _controller,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _submit(),
            decoration: InputDecoration(
              hintText: strings.amountEntryHint,
              errorText: _error,
            ),
          ),
        ],
      ),
    );
  }
}

/// A titled task card for the verification and recovery surfaces: a state, a
/// next step, and a client-owned action. The label is prewritten static chrome
/// (screens.md: the shell and static chrome are not composed), so it comes from
/// the client strings, not the agent's payload.
class _TaskCard extends ConsumerWidget {
  const _TaskCard({
    required this.title,
    this.body,
    this.status,
    this.actionKind,
    this.onAction,
  });

  final String title;
  final String? body;
  final String? status;

  /// `verification` or `recovery`; selects the client-owned action label.
  final String? actionKind;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = SabColorTokens.of(context);
    final strings = ref.watch(sabStringsProvider);
    final label = switch (actionKind) {
      // The identity ceremony finishes on the Identity screen, so the action
      // names that screen rather than implying it completes inline.
      'verification' => strings.openVerificationScreen,
      'recovery' => strings.openCase,
      _ => null,
    };
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
          Text(
            title,
            style: SabTypography.body.copyWith(
              color: colors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (body != null && body!.isNotEmpty) ...[
            const SizedBox(height: SabSpacing.xs),
            Text(
              body!,
              style: SabTypography.bodySmall.copyWith(
                color: colors.textSecondary,
              ),
            ),
          ],
          if (status != null) ...[
            const SizedBox(height: SabSpacing.sm),
            StatusPill(status: _statusFrom(status)),
          ],
          if (label != null && onAction != null) ...[
            const SizedBox(height: SabSpacing.sm),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton(
                onPressed: onAction,
                child: Text(
                  label,
                  style: SabTypography.body.copyWith(
                    color: colors.primary500,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Resolves two numeric bindings (amount/charges, minimum/maximum) before
/// building, so a `{path: ...}` value from the agent is honoured. [BoundNumber]
/// handles a literal, a path binding, and a function call alike.
class _BoundNumbers extends StatelessWidget {
  const _BoundNumbers({
    required this.dataContext,
    required this.amount,
    required this.charges,
    required this.builder,
  });

  final DataContext dataContext;
  final Object? amount;
  final Object? charges;
  final Widget Function(int? amount, int? charges) builder;

  @override
  Widget build(BuildContext context) {
    return BoundNumber(
      dataContext: dataContext,
      value: amount,
      builder: (context, resolvedAmount) => BoundNumber(
        dataContext: dataContext,
        value: charges,
        builder: (context, resolvedCharges) =>
            builder(resolvedAmount?.toInt(), resolvedCharges?.toInt()),
      ),
    );
  }
}
