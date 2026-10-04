import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sabi_mobile/core/api_client.dart';
import 'package:sabi_mobile/core/api_config.dart';
import 'package:sabi_mobile/core/api_providers.dart';
import 'package:sabi_mobile/data/http_repositories.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/payment/data/providers.dart';
import 'package:sabi_mobile/features/payment/models/payment.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/intent_result.dart';

const _config = ApiConfig(baseUrl: 'http://10.0.2.2:8000/v1');

class _StubClient extends http.BaseClient {
  _StubClient(this.statusCode, this.body, {this.capture});

  final int statusCode;
  final String body;
  final void Function(http.BaseRequest request)? capture;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    capture?.call(request);
    return http.StreamedResponse(
      Stream.value(utf8.encode(body)),
      statusCode,
      headers: {'content-type': 'application/json'},
    );
  }
}

SabApiClient _api(int status, Object body) => SabApiClient(
  config: _config,
  httpClient: _StubClient(status, jsonEncode(body)),
);

/// A catalogue double whose detail always returns [service].
class _FixedCatalogue implements CatalogueRepository {
  _FixedCatalogue(this.service);

  final CatalogueService service;

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async => service;

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  }) async => throw UnimplementedError();

  @override
  Future<CatalogueSearchResult> search(String query) async =>
      throw UnimplementedError();
}

CatalogueService _service(String type) => CatalogueService(
  id: 'svc_1',
  type: type,
  name: 'Service',
  collectingBody: 'Collecting Body',
  category: 'Government',
  knownAmount: type == 'merchant' ? null : 250000,
);

ProviderContainer _liveContainer(CatalogueService service) {
  final container = ProviderContainer(
    overrides: [
      apiConfigProvider.overrideWithValue(
        const ApiConfig(baseUrl: 'http://x/v1', useLiveRepositories: true),
      ),
      catalogueRepositoryProvider.overrideWith(
        (ref) => _FixedCatalogue(service),
      ),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

void main() {
  group('HttpCatalogueRepository.resolveIntent history (C-009 rev 3)', () {
    test('carries the prior conversation oldest first', () async {
      http.BaseRequest? captured;
      final repo = HttpCatalogueRepository(
        SabApiClient(
          config: _config,
          httpClient: _StubClient(
            200,
            jsonEncode({
              'intent': {'intentType': 'unknown', 'confidence': 0.5},
              'candidates': const [],
              'source': 'model',
            }),
            capture: (request) => captured = request,
          ),
        ),
      );
      await repo.resolveIntent(
        text: 'the second turn',
        locale: AppLocale.english,
        history: const [
          IntentHistoryTurn(role: 'user', text: 'the first turn'),
          IntentHistoryTurn(role: 'assistant', text: 'Which one?'),
        ],
      );
      final body =
          jsonDecode((captured as http.Request).body) as Map<String, dynamic>;
      expect(body['history'], [
        {'role': 'user', 'text': 'the first turn'},
        {'role': 'assistant', 'text': 'Which one?'},
      ]);
    });

    test('omits history when there is none', () async {
      http.BaseRequest? captured;
      final repo = HttpCatalogueRepository(
        SabApiClient(
          config: _config,
          httpClient: _StubClient(
            200,
            jsonEncode({
              'intent': {'intentType': 'non_command', 'confidence': 0.2},
              'candidates': const [],
              'source': 'model',
            }),
            capture: (request) => captured = request,
          ),
        ),
      );
      final intent = await repo.resolveIntent(
        text: 'Hello',
        locale: AppLocale.english,
        history: const [],
      );
      expect(intent.isNonCommand, isTrue);
      final body =
          jsonDecode((captured as http.Request).body) as Map<String, dynamic>;
      expect(body.containsKey('history'), isFalse);
    });
  });

  group('HttpCatalogueRepository.serviceDetail (C-011)', () {
    test('a 200 parses the full Service', () async {
      final repo = HttpCatalogueRepository(
        _api(200, {
          'service': {
            'id': 'svc_lagos_land_use',
            'type': 'government',
            'name': 'Land Use Charge',
            'collectingBody': 'Lagos State Government',
            'category': 'Government',
            'aliases': ['LUC'],
            'providerId': 'prv_1',
            'capabilityId': 'cap_1',
            'knownAmount': 2500000,
            'currency': 'NGN',
            'status': 'active',
          },
        }),
      );
      final service = await repo.serviceDetail('svc_lagos_land_use');
      expect(service.id, 'svc_lagos_land_use');
      expect(service.type, 'government');
      expect(service.collectingBody, 'Lagos State Government');
      expect(service.knownAmount, 2500000);
      expect(service.aliases, ['LUC']);
    });

    test('a 404 is an unknown service', () {
      final repo = HttpCatalogueRepository(
        _api(404, {
          'error': {'code': 'not_found', 'message': 'Unknown.'},
        }),
      );
      expect(
        () => repo.serviceDetail('svc_missing'),
        throwsA(isA<ServiceNotFoundException>()),
      );
    });
  });

  group('MockCatalogueRepository.serviceDetail', () {
    test('resolves a seeded service with its type', () async {
      final repo = MockCatalogueRepository(latency: Duration.zero);
      final service = await repo.serviceDetail('svc_mtn_airtime');
      expect(service.type, 'biller');
      expect(service.knownAmount, 200000);
    });

    test('an unknown service is a 404', () {
      final repo = MockCatalogueRepository(latency: Duration.zero);
      expect(
        () => repo.serviceDetail('svc_missing'),
        throwsA(isA<ServiceNotFoundException>()),
      );
    });
  });

  group('paymentObligationProvider derives the flow from the service type', () {
    test('government uses the federal flow', () async {
      final container = _liveContainer(_service('government'));
      final obligation = await container.read(
        paymentObligationProvider('svc_1').future,
      );
      expect(obligation.kind, PaymentKind.federal);
      expect(obligation.knownAmount, 250000);
    });

    test('biller uses the everyday bill flow', () async {
      final container = _liveContainer(_service('biller'));
      final obligation = await container.read(
        paymentObligationProvider('svc_1').future,
      );
      expect(obligation.kind, PaymentKind.bill);
    });

    test('merchant uses the standard flow', () async {
      final container = _liveContainer(_service('merchant'));
      final obligation = await container.read(
        paymentObligationProvider('svc_1').future,
      );
      expect(obligation.kind, PaymentKind.standard);
      expect(obligation.isVariable, isTrue);
    });

    test('the mock build resolves from the sandbox', () async {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      final obligation = await container.read(
        paymentObligationProvider('svc_ikeja_electric').future,
      );
      expect(obligation.kind, PaymentKind.bill);
      expect(obligation.service.collectingBody, 'Ikeja Electric');
    });
  });
}
