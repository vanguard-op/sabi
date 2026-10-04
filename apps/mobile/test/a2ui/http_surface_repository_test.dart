import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sabi_mobile/a2ui/http_surface_repository.dart';
import 'package:sabi_mobile/a2ui/sabi_catalog.dart';
import 'package:sabi_mobile/a2ui/surface_task.dart';
import 'package:sabi_mobile/core/api_client.dart';
import 'package:sabi_mobile/core/api_config.dart';

const _config = ApiConfig(baseUrl: 'http://10.0.2.2:8000/v1');

/// Captures the request so the C-012 body can be asserted.
class _RecordingClient extends http.BaseClient {
  _RecordingClient(this.body);

  final Object body;
  http.BaseRequest? lastRequest;
  String? lastBody;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    lastRequest = request;
    if (request is http.Request) lastBody = request.body;
    return http.StreamedResponse(
      Stream.value(utf8.encode(jsonEncode(body))),
      200,
      headers: {'content-type': 'application/json'},
    );
  }
}

void main() {
  test('compose posts task, context, and the published catalogId (C-012)', () async {
    final client = _RecordingClient({
      'messages': [
        {
          'version': 'v0.9',
          'createSurface': {
            'surfaceId': 'confirmation_1',
            'catalogId': SabiCatalog.catalogId,
          },
        },
      ],
      'fallback': 'confirmation',
    });
    final api = SabApiClient(config: _config, httpClient: client);
    final repo = HttpSurfaceRepository(api);

    final body = await repo.compose(
      const SurfaceRequest(
        task: SurfaceTask.confirmation,
        context: {'amount': 2500000, 'payee': 'Lagos State Government'},
      ),
    );

    expect(client.lastRequest?.url.path, endsWith('/agent/surfaces'));
    final sent =
        jsonDecode(client.lastBody!) as Map<String, dynamic>;
    expect(sent['task'], 'confirmation');
    expect(sent['catalogId'], SabiCatalog.catalogId);
    expect((sent['context'] as Map)['amount'], 2500000);
    expect(body['fallback'], 'confirmation');
  });
}
