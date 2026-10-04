import '../core/api_client.dart';
import '../core/api_exception.dart';
import 'surface_repository.dart';
import 'surface_task.dart';

/// Live agent composition (FEAT-011, C-012 revision 2). POSTs the task, its
/// context, and the client's published `catalogId` to the agent, and returns
/// the A2UI message stream. The contract answers 200 with a `fallback` when
/// composition fails, so a non-200 is a transport or session failure the caller
/// handles with the same fallback.
class HttpSurfaceRepository implements SurfaceRepository {
  HttpSurfaceRepository(this._api);

  final SabApiClient _api;

  @override
  Future<Map<String, dynamic>> compose(SurfaceRequest request) async {
    try {
      return await _api.post('/agent/surfaces', body: request.toJson());
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }
}
