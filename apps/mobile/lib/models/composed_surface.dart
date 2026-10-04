import 'package:flutter/foundation.dart';

/// The tasks the agent may compose (CONTRACTS.md C-012 `task`, revision 1).
///
/// `receipt` covers both a post-payment receipt and a resolved record the user
/// asked about: the task is the same and the resolved record reference rides in
/// `context`. `verification` and `recovery` are the identity and failed-payment
/// task surfaces (FEAT-002/FEAT-009, FEAT-011).
enum SurfaceTask {
  confirmation,
  amountEntry,
  receipt,
  discovery,
  verification,
  recovery;

  /// The wire value, so a request or fallback never invents one.
  String get wire => switch (this) {
    SurfaceTask.confirmation => 'confirmation',
    SurfaceTask.amountEntry => 'amount_entry',
    SurfaceTask.receipt => 'receipt',
    SurfaceTask.discovery => 'discovery',
    SurfaceTask.verification => 'verification',
    SurfaceTask.recovery => 'recovery',
  };

  static SurfaceTask? parse(String? raw) => switch (raw) {
    'confirmation' => SurfaceTask.confirmation,
    'amount_entry' || 'amountEntry' => SurfaceTask.amountEntry,
    'receipt' => SurfaceTask.receipt,
    'discovery' => SurfaceTask.discovery,
    'verification' => SurfaceTask.verification,
    'recovery' => SurfaceTask.recovery,
    _ => null,
  };
}

/// Maps a component name from either side of the wire to the client's catalogue
/// type. The declarative stream may name a component in the client's camelCase
/// type (`confirmationSummary`) or by the shared catalogue's PascalCase name
/// (`ConfirmationSummary`); both resolve to the one catalogue entry the client
/// renders, so a composition naming either is not refused for casing alone.
String? _catalogueType(String raw) => switch (raw) {
  'text' || 'Text' => 'text',
  'confirmationSummary' || 'ConfirmationSummary' => 'confirmationSummary',
  'serviceResultRow' || 'ServiceResultRow' => 'serviceResultRow',
  'receiptCard' || 'ReceiptCard' => 'receiptCard',
  'statusPill' || 'StatusPill' => 'statusPill',
  'amountEntry' || 'AmountEntry' => 'amountEntry',
  _ => null,
};

/// One component requested by the agent. [type] is normalized to a client
/// catalogue type; an unknown name stays as received so the renderer can refuse
/// it and show the fallback form.
@immutable
class SurfaceComponent {
  const SurfaceComponent({required this.type, this.data = const {}});

  final String type;
  final Map<String, dynamic> data;

  factory SurfaceComponent.fromJson(Map<String, dynamic> json) {
    final rawData = json['data'] ?? json['props'];
    final rawName = (json['type'] ?? json['component'] ?? '').toString();
    return SurfaceComponent(
      type: _catalogueType(rawName) ?? rawName,
      data: rawData is Map ? rawData.cast<String, dynamic>() : const {},
    );
  }
}

/// A validated agent-composed surface (CONTRACTS.md C-012).
///
/// Built from the declarative stream (`createSurface`, `updateComponents`,
/// `updateDataModel`). Parsing is deliberately forgiving: a malformed message is
/// discarded rather than failing the task, partial data renders as placeholders,
/// and a surface with no recognised task or component is handed to the fallback
/// form so the task stays completable (FEAT-011).
@immutable
class ComposedSurface {
  const ComposedSurface({
    required this.surfaceId,
    this.task,
    this.components = const [],
    this.data = const {},
    this.fallback,
  });

  final String surfaceId;
  final SurfaceTask? task;
  final List<SurfaceComponent> components;
  final Map<String, dynamic> data;

  /// The task key to fall back to when composition fails.
  final String? fallback;

  /// A resolved record reference carried in `context` for a `receipt` task: an
  /// identifier for the record the surface is about. Null for a post-payment
  /// receipt or any other task.
  String? get recordRef {
    final raw = data['recordRef'] ?? data['receiptId'] ?? data['caseId'];
    final text = raw?.toString();
    return (text == null || text.isEmpty) ? null : text;
  }

  /// Whether every requested component is in the client catalogue.
  bool isRenderable(Set<String> catalogue) =>
      task != null && components.every((c) => catalogue.contains(c.type));

  static ComposedSurface? parse(Map<String, dynamic> json) {
    final messages = (json['messages'] as List?) ?? const [];
    String? surfaceId;
    SurfaceTask? task;
    var components = <SurfaceComponent>[];
    var data = <String, dynamic>{};
    for (final raw in messages) {
      if (raw is! Map) continue;
      final message = raw.cast<String, dynamic>();
      switch (message['type']) {
        case 'createSurface':
          surfaceId = message['surfaceId']?.toString();
          task = SurfaceTask.parse(message['task']?.toString());
          break;
        case 'updateComponents':
          final list = (message['components'] as List?) ?? const [];
          components = list
              .whereType<Map>()
              .map((e) => SurfaceComponent.fromJson(e.cast<String, dynamic>()))
              .toList(growable: false);
          break;
        case 'updateDataModel':
          final update = message['data'];
          if (update is Map) {
            data = {...data, ...update.cast<String, dynamic>()};
          }
          break;
        default:
          // Unknown message type: discard it, keep the task.
          break;
      }
    }
    return ComposedSurface(
      surfaceId: surfaceId ?? '',
      task: task,
      components: components,
      data: data,
      fallback: json['fallback']?.toString(),
    );
  }
}
