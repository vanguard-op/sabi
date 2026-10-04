import 'surface_task.dart';

/// Agent-composed task surfaces (FEAT-011, C-012 revision 2).
///
/// Asks the agent for the A2UI message stream that renders [request] against
/// the client's published catalog. It returns the raw C-012 response body
/// (messages and fallback); the caller gates it with `A2uiGate` and renders it
/// through the GenUI SDK. It never throws for a composition failure: the
/// contract answers 200 with a fallback, and a transport failure is surfaced so
/// the caller can use the same fallback.
abstract class SurfaceRepository {
  Future<Map<String, dynamic>> compose(SurfaceRequest request);
}
