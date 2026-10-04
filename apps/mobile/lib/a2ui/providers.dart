import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_providers.dart';
import 'http_surface_repository.dart';
import 'mock_surface_repository.dart';
import 'surface_repository.dart';

/// Agent composition of task surfaces (FEAT-011, C-012 revision 2). The live
/// implementation posts to `/agent/surfaces` with the published `catalogId`;
/// the mock authors the same catalog-conforming streams so the client's gate,
/// renderer, and fallback are exercisable without the live agent.
final surfaceRepositoryProvider = Provider<SurfaceRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpSurfaceRepository(ref.watch(apiClientProvider));
  }
  return MockSurfaceRepository();
});
