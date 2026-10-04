import 'sabi_catalog.dart';
import 'surface_repository.dart';
import 'surface_task.dart';

/// Mock agent composition (FEAT-011, C-012 revision 2). It authors real v0.9
/// A2UI streams against the published Sabi catalog from the request context, so
/// the client's catalog, gate, renderer, and fallback are all exercisable
/// without the live agent. Each stream uses only catalog components and carries
/// a `root`, exactly as the agent's composition must.
class MockSurfaceRepository implements SurfaceRepository {
  MockSurfaceRepository({
    this.latency = const Duration(milliseconds: 350),
    this.failNext = false,
  });

  Duration latency;
  bool failNext;

  int _surfaceSequence = 0;

  @override
  Future<Map<String, dynamic>> compose(SurfaceRequest request) async {
    await Future<void>.delayed(latency);
    if (failNext) {
      failNext = false;
      // C-012 answers 200 with a fallback on a composition failure; the client
      // renders its fallback form for the same task.
      return _fallback(request);
    }

    _surfaceSequence++;
    final surfaceId = '${request.task.wire}_$_surfaceSequence';
    final context = request.context;

    switch (request.task) {
      case SurfaceTask.confirmation:
        return _stream(surfaceId, request.task, [
          {
            'id': 'root',
            'component': SabiCatalog.confirmationSummary.value,
            'amount': (context['amount'] as num?)?.toInt() ?? 0,
            'currency': context['currency']?.toString() ?? 'NGN',
            'payee': context['payee']?.toString() ?? '',
            if (context['reference'] != null)
              'reference': context['reference'].toString(),
          },
        ]);
      case SurfaceTask.amountEntry:
        return _stream(surfaceId, request.task, [
          {
            'id': 'root',
            'component': SabiCatalog.amountEntry.value,
            'currency': context['currency']?.toString() ?? 'NGN',
            if (context['minimum'] != null)
              'minimum': (context['minimum'] as num).toInt(),
            if (context['maximum'] != null)
              'maximum': (context['maximum'] as num).toInt(),
          },
        ]);
      case SurfaceTask.receipt:
        return _stream(surfaceId, request.task, [
          {
            'id': 'root',
            'component': SabiCatalog.receiptCard.value,
            if (context['receiptId'] != null)
              'receiptId': context['receiptId'].toString(),
            'reference': context['reference']?.toString() ?? '',
            'payee': context['payee']?.toString() ?? '',
            'amount': (context['amount'] as num?)?.toInt() ?? 0,
            'currency': context['currency']?.toString() ?? 'NGN',
            'issuedAt': context['issuedAt']?.toString() ?? '',
            'kind': context['kind']?.toString() ?? '',
            'status': context['status']?.toString() ?? 'pending',
          },
        ]);
      case SurfaceTask.discovery:
        final services = (context['services'] as List?) ?? const [];
        final rows = [
          for (final service in services) _catalogService(service as Map),
        ];
        // A2UI is an adjacency list: only components reachable from the single
        // `root` render. One result is a ServiceResultRow; several are a
        // ProviderPicker whose `services` array is the root's own data.
        if (rows.length == 1) {
          return _stream(surfaceId, request.task, [
            {
              'id': 'root',
              'component': SabiCatalog.serviceResultRow.value,
              ...rows.single,
            },
          ]);
        }
        return _stream(surfaceId, request.task, [
          {
            'id': 'root',
            'component': SabiCatalog.providerPicker.value,
            'services': rows,
          },
        ]);
      case SurfaceTask.verification:
        return _stream(surfaceId, request.task, [
          {
            'id': 'root',
            'component': SabiCatalog.verification.value,
            'title': context['title']?.toString() ?? '',
            if (context['body'] != null) 'body': context['body'].toString(),
          },
        ]);
      case SurfaceTask.recovery:
        return _stream(surfaceId, request.task, [
          {
            'id': 'root',
            'component': SabiCatalog.recovery.value,
            'title': context['title']?.toString() ?? '',
            if (context['body'] != null) 'body': context['body'].toString(),
            if (context['status'] != null)
              'status': context['status'].toString(),
          },
        ]);
    }
  }

  Map<String, dynamic> _stream(
    String surfaceId,
    SurfaceTask task,
    List<Map<String, Object?>> components,
  ) {
    final composition = A2uiComposition(
      surfaceId: surfaceId,
      task: task,
      components: components,
    );
    return {
      'messages': composition.messages(),
      'fallback': task.wire,
      'context': const <String, dynamic>{},
    };
  }

  Map<String, dynamic> _fallback(SurfaceRequest request) => {
    'messages': const <Map<String, dynamic>>[],
    'fallback': request.task.wire,
    'context': const <String, dynamic>{},
  };
}

/// A service in the camelCase shape the published catalog's ServiceResultRow
/// exposes. The mock's context carries the wire (snake_case) form, so it is
/// mapped here; a live agent composes the same shape.
Map<String, Object?> _catalogService(Map<dynamic, dynamic> raw) => {
  'serviceId': (raw['service_id'] ?? raw['serviceId'] ?? '').toString(),
  'name': (raw['name'] ?? '').toString(),
  'collectingBody': (raw['collecting_body'] ?? raw['collectingBody'] ?? '')
      .toString(),
  'category': (raw['category'] ?? '').toString(),
  if ((raw['known_amount'] ?? raw['knownAmount']) != null)
    'knownAmount': ((raw['known_amount'] ?? raw['knownAmount']) as num).toInt(),
  'currency': (raw['currency'] ?? 'NGN').toString(),
  'status': (raw['status'] ?? 'active').toString(),
  'confidence': ((raw['confidence'] as num?) ?? 0).toDouble(),
};
