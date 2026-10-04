import 'dart:async';
import 'dart:convert';

import 'package:a2ui_core/a2ui_core.dart' as core;
import 'package:flutter/material.dart';
import 'package:genui/genui.dart';

import 'sabi_catalog.dart';

/// The outcome of gating an incoming A2UI message stream on the client, before
/// anything is rendered. This is the client-side phase of A2UI's two-phase
/// validation (FEAT-011, MQ-003): a stream that does not conform is refused and
/// the caller renders the prewritten fallback for the same task.
enum A2uiGateResult {
  /// Every message parses, names the published catalog, uses catalog
  /// components, and provides a `root` component.
  accepted,

  /// A message is malformed, names another catalog, requests an unknown
  /// component, or provides no root.
  rejected,
}

/// A parsed, gated A2UI stream ready to feed the renderer.
@immutable
class A2uiSurfaceStream {
  const A2uiSurfaceStream({
    required this.surfaceId,
    required this.task,
    required this.messages,
    required this.fallback,
    this.recordRef,
  });

  final String surfaceId;

  /// The task key the surface is composed for (`confirmation`, `amount_entry`,
  /// `receipt`, `discovery`, `verification`, `recovery`). Null when the agent
  /// named no task, so the caller falls back.
  final String? task;
  final List<core.A2uiMessage> messages;

  /// The task key to fall back to when composition fails.
  final String? fallback;

  /// A resolved-record identifier carried for a `receipt` surface.
  final String? recordRef;

  static const String catalogId = SabiCatalog.catalogId;
}

/// Gating errors, so the caller can report the reason to the agent.
class A2uiGateException implements Exception {
  const A2uiGateException(this.message, {this.surfaceId, this.path});

  final String message;
  final String? surfaceId;
  final String? path;

  @override
  String toString() => message;
}

/// The client-side gate for one incoming A2UI response (C-012 revision 2).
///
/// Parses `messages` into typed A2UI messages and refuses the stream unless it
/// is well-formed for the published catalog. The check is deliberately strict
/// on the four things the client must own: the message version, the negotiated
/// catalog id, the component names, and the presence of a `root`. Deeper schema
/// validation is performed by the renderer itself against the same catalog and
/// surfaces as `VALIDATION_FAILED`.
abstract final class A2uiGate {
  A2uiGate._();

  static A2uiSurfaceStream gate(
    Map<String, dynamic> body, {
    required bool Function(String component) defines,
    String? task,
  }) {
    final rawMessages = body['messages'];
    if (rawMessages is! List) {
      throw const A2uiGateException('A2UI response carries no messages array.');
    }

    final messages = <core.A2uiMessage>[];
    final surfaceIds = <String>[];
    var sawRoot = false;

    for (final raw in rawMessages) {
      if (raw is! Map) {
        throw const A2uiGateException('An A2UI message is not an object.');
      }
      final map = raw.cast<String, dynamic>();
      final core.A2uiMessage message;
      try {
        message = core.A2uiMessage.fromJson(map);
      } on core.A2uiValidationError catch (e) {
        throw A2uiGateException(e.message);
      }
      switch (message) {
        case core.CreateSurfaceMessage():
          surfaceIds.add(message.surfaceId);
          if (message.catalogId != SabiCatalog.catalogId) {
            throw A2uiGateException(
              'Surface names catalog "${message.catalogId}", not the published '
              'catalog.',
              surfaceId: message.surfaceId,
              path: 'createSurface/catalogId',
            );
          }
        case core.UpdateComponentsMessage():
          for (final component in message.components) {
            final name = component['component']?.toString() ?? '';
            if (name.isEmpty) {
              throw A2uiGateException(
                'A component carries no "component" type.',
                surfaceId: message.surfaceId,
                path: 'updateComponents',
              );
            }
            if (!defines(name)) {
              throw A2uiGateException(
                'Component "$name" is not in the published catalog.',
                surfaceId: message.surfaceId,
                path: 'updateComponents/components/$name',
              );
            }
            if (component['id'] == 'root') sawRoot = true;
          }
        case core.UpdateDataModelMessage():
        case core.DeleteSurfaceMessage():
          break;
      }
      messages.add(message);
    }

    if (surfaceIds.isEmpty) {
      throw const A2uiGateException('The stream creates no surface.');
    }
    if (!sawRoot) {
      throw A2uiGateException(
        'The surface has no "root" component.',
        surfaceId: surfaceIds.first,
        path: 'updateComponents',
      );
    }

    return A2uiSurfaceStream(
      surfaceId: surfaceIds.first,
      task: task ?? (body['task'] as String?)?.trim(),
      messages: messages,
      fallback: body['fallback']?.toString(),
      recordRef: _recordRef(body),
    );
  }

  static String? _recordRef(Map<String, dynamic> body) {
    final context = body['context'];
    if (context is! Map) return null;
    for (final key in ['recordRef', 'receiptId', 'caseId']) {
      final value = context[key]?.toString();
      if (value != null && value.isNotEmpty) return value;
    }
    return null;
  }
}

/// Renders an agent-composed A2UI surface through the official Flutter GenUI
/// SDK (FEAT-011), or the caller's prewritten fallback for the same task.
///
/// Owns the [SurfaceController], feeds it the gated messages, and renders a
/// [Surface] bound to the controller's context. The `genui` package is alpha,
/// so the fallback carries the task whenever the stream is refused, the SDK
/// cannot render, or the surface fails the SDK's own catalog validation (which
/// is reported back to the agent as `VALIDATION_FAILED`).
class A2uiSurfaceView extends StatefulWidget {
  const A2uiSurfaceView({
    super.key,
    required this.stream,
    required this.fallback,
    this.onValidationFailed,
    this.onAction,
  });

  /// The gated stream to render, or null when the response was refused before
  /// reaching the renderer.
  final A2uiSurfaceStream? stream;

  /// The prewritten text-and-form fallback for the same task. Rendered when the
  /// SDK is unavailable, the stream is refused, or rendering fails.
  final WidgetBuilder fallback;

  /// Called with the A2UI error envelope when the SDK reports a client-side
  /// validation failure, so the caller can forward `VALIDATION_FAILED` to the
  /// agent (A2UI client-to-server error reporting).
  final void Function(Map<String, Object?> error)? onValidationFailed;

  /// Called when a catalog component dispatches a user action. The action name
  /// and its context are the agent-facing shape; the host routes it to the
  /// screen behaviour (selecting a service, opening a record).
  final void Function(A2uiAction action)? onAction;

  @override
  State<A2uiSurfaceView> createState() => _A2uiSurfaceViewState();
}

/// A user action dispatched by a catalog component (A2UI actions).
@immutable
class A2uiAction {
  const A2uiAction({required this.name, required this.context});

  final String name;
  final Map<String, Object?> context;
}

class _A2uiSurfaceViewState extends State<A2uiSurfaceView> {
  SurfaceController? _controller;
  StreamSubscription<ChatMessage>? _reports;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _attach();
  }

  @override
  void didUpdateWidget(covariant A2uiSurfaceView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.stream != widget.stream) {
      _detach();
      _attach();
    }
  }

  void _attach() {
    final stream = widget.stream;
    if (stream == null) {
      _failed = true;
      return;
    }
    try {
      final controller = SurfaceController(catalogs: [sabiCatalog]);
      _reports = controller.onSubmit.listen(_onReport);
      for (final message in stream.messages) {
        controller.handleMessage(message);
      }
      _controller = controller;
      _failed = false;
    } catch (_) {
      // The SDK rejected a message outright: fall back rather than crash.
      _failed = true;
    }
  }

  void _onReport(ChatMessage message) {
    for (final part in message.parts) {
      final interaction = part.asUiInteractionPart;
      if (interaction == null) continue;
      final decoded = _decode(interaction.interaction);
      if (decoded == null) continue;
      if (decoded['code']?.toString() == 'VALIDATION_FAILED') {
        if (mounted) setState(() => _failed = true);
        widget.onValidationFailed?.call(decoded);
      }
    }
  }

  Map<String, Object?>? _decode(String raw) {
    final decoded = jsonDecode(raw);
    if (decoded is! Map) return null;
    final error = decoded['error'];
    return error is Map ? error.cast<String, Object?>() : null;
  }

  void _detach() {
    _reports?.cancel();
    _reports = null;
    _controller?.dispose();
    _controller = null;
  }

  @override
  void dispose() {
    _detach();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    final stream = widget.stream;
    if (!a2uiSdkAvailable || _failed || controller == null || stream == null) {
      return widget.fallback(context);
    }
    return Surface(
      surfaceContext: controller.contextFor(stream.surfaceId),
      actionDelegate: _SabiActionDelegate(widget.onAction),
    );
  }
}

/// Routes a catalog component's user action to the host. A component that
/// dispatches an action is handled here rather than being sent to the agent, so
/// the host can drive its own behaviour (selecting a service, opening a record)
/// while the surface still names the action the agent understands.
class _SabiActionDelegate implements ActionDelegate {
  const _SabiActionDelegate(this.onAction);

  final void Function(A2uiAction action)? onAction;

  @override
  bool handleEvent(
    BuildContext context,
    UiEvent event,
    SurfaceContext genUiContext,
    Widget Function(SurfaceDefinition, Catalog, String, DataContext)
    buildWidget,
  ) {
    final handler = onAction;
    if (handler == null || !event.isUserAction) return false;
    final action = UserActionEvent.fromMap(event.toMap());
    handler(A2uiAction(name: action.name, context: action.context));
    return true;
  }
}

/// Whether the GenUI SDK is available to the client. The alpha SDK can be
/// compiled out or fail to load; the caller consults this so a task never
/// depends on it (FEAT-011 fallback). It is a constant today because the
/// package is a direct dependency; it exists as a seam so a build that drops
/// `genui` flips every surface to its fallback.
const bool a2uiSdkAvailable = true;
