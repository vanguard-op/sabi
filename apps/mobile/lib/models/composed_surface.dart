import 'package:flutter/foundation.dart';

/// The tasks the agent may compose (CONTRACTS.md C-012 `task`).
enum SurfaceTask {
  confirmation,
  amountEntry,
  receipt,
  discovery;

  static SurfaceTask? parse(String? raw) => switch (raw) {
    'confirmation' => SurfaceTask.confirmation,
    'amount_entry' || 'amountEntry' => SurfaceTask.amountEntry,
    'receipt' => SurfaceTask.receipt,
    'discovery' => SurfaceTask.discovery,
    _ => null,
  };
}

/// One component requested by the agent. [type] must be in the client catalogue;
/// the renderer refuses anything it does not know and shows the fallback form.
@immutable
class SurfaceComponent {
  const SurfaceComponent({required this.type, this.data = const {}});

  final String type;
  final Map<String, dynamic> data;

  factory SurfaceComponent.fromJson(Map<String, dynamic> json) {
    final rawData = json['data'] ?? json['props'];
    return SurfaceComponent(
      type: (json['type'] ?? '').toString(),
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
