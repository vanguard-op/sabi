import 'package:flutter/foundation.dart';

import 'sabi_catalog.dart';

/// The tasks the agent may compose (CONTRACTS.md C-012 revision 2 `task`).
///
/// `receipt` covers both a post-payment receipt and a resolved record the user
/// asked about: the task is the same and the resolved record reference rides in
/// the request `context`. `verification` and `recovery` are the identity and
/// failed-payment task surfaces (FEAT-002/FEAT-009, FEAT-011). The shell
/// (composer, navigation, static chrome) is never a task.
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

/// A request for a task surface (C-012 revision 2).
///
/// [catalogId] is the client's published Sabi A2UI catalog, negotiated from the
/// `supportedCatalogIds` the client advertises. [context] is the untrusted,
/// free-form task context (amount, payee, candidates, record reference); it is
/// data the agent composes with, never a composition rule.
@immutable
class SurfaceRequest {
  const SurfaceRequest({
    required this.task,
    this.context = const {},
  });

  final SurfaceTask task;
  final Map<String, dynamic> context;

  /// The published catalog the client requests composition against.
  static const String catalogId = SabiCatalog.catalogId;

  Map<String, dynamic> toJson() => {
    'task': task.wire,
    'context': context,
    'catalogId': SabiCatalog.catalogId,
  };
}

/// The A2UI JSON component for one task surface, so a widget test or a mock can
/// assert composition without re-deriving the shape.
@immutable
class A2uiComposition {
  const A2uiComposition({
    required this.surfaceId,
    required this.task,
    required this.components,
    this.dataModel = const {},
  });

  final String surfaceId;
  final SurfaceTask task;

  /// The flat v0.9 component list, with a `root` component.
  final List<Map<String, Object?>> components;
  final Map<String, Object?> dataModel;

  /// The v0.9 message stream for this surface. The root is `ConfirmationSummary`
  /// or whichever component the task renders first; every child is id-
  /// referenced, as A2UI's adjacency list requires.
  List<Map<String, Object?>> messages() => [
    {
      'version': 'v0.9',
      'createSurface': {
        'surfaceId': surfaceId,
        'catalogId': SabiCatalog.catalogId,
      },
    },
    {
      'version': 'v0.9',
      'updateComponents': {
        'surfaceId': surfaceId,
        'components': components,
      },
    },
    if (dataModel.isNotEmpty)
      {
        'version': 'v0.9',
        'updateDataModel': {
          'surfaceId': surfaceId,
          'path': '/',
          'value': dataModel,
        },
      },
  ];
}
