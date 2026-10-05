import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/a2ui/sabi_catalog.dart';
import 'package:sabi_mobile/models/service_summary.dart';

ServiceSummary _service({
  String serviceId = 'svc_lagos',
  String name = 'Land Use Charge',
  String collectingBody = 'Lagos State Government',
  String category = 'Government',
  int? knownAmount = 2500000,
  String currency = 'NGN',
  String status = 'active',
  double confidence = 0.92,
}) => ServiceSummary(
  serviceId: serviceId,
  name: name,
  collectingBody: collectingBody,
  category: category,
  knownAmount: knownAmount,
  currency: currency,
  status: status,
  confidence: confidence,
);

/// The `ServiceResultRow` schema the agent composes discovery against, read from
/// the single authored catalog document (FEAT-011, C-012).
Map<String, Object?> _serviceResultRowSchema() =>
    ((SabiCatalog.document()['components'] as Map)['ServiceResultRow'] as Map)
        .cast<String, Object?>();

void main() {
  group('ServiceSummary.toJson', () {
    test('emits the catalog ServiceResultRow camelCase keys, not snake_case', () {
      final json = _service().toJson();
      final schema = _serviceResultRowSchema();
      final properties = (schema['properties'] as Map).keys.cast<String>();

      expect(json.keys.toSet(), properties.toSet());
      // The former snake_case keys must be gone from the wire.
      expect(json.containsKey('service_id'), isFalse);
      expect(json.containsKey('collecting_body'), isFalse);
      expect(json.containsKey('known_amount'), isFalse);
      expect(json['serviceId'], 'svc_lagos');
      expect(json['collectingBody'], 'Lagos State Government');
      expect(json['knownAmount'], 2500000);
    });

    test('carries every value through unchanged', () {
      final json = _service(
        serviceId: 'svc_ikeja',
        name: 'Electricity',
        collectingBody: 'Ikeja Electric',
        category: 'Utility',
        knownAmount: null,
        currency: 'NGN',
        status: 'active',
        confidence: 0.5,
      ).toJson();

      expect(json, {
        'serviceId': 'svc_ikeja',
        'name': 'Electricity',
        'collectingBody': 'Ikeja Electric',
        'category': 'Utility',
        'knownAmount': null,
        'currency': 'NGN',
        'status': 'active',
        'confidence': 0.5,
      });
    });

    test('a null knownAmount is still a wire key shaped as integer|null', () {
      final json = _service(knownAmount: null).toJson();
      final schema = _serviceResultRowSchema();
      final knownAmount = (schema['properties'] as Map)['knownAmount'] as Map;

      expect(json.containsKey('knownAmount'), isTrue);
      expect(json['knownAmount'], isNull);
      expect((knownAmount['type'] as List).contains('null'), isTrue);
    });
  });

  group('discovery context against the composition schema', () {
    test('summaries serialised into the discovery context satisfy the catalog '
        'ServiceResultRow required fields', () {
      final schema = _serviceResultRowSchema();
      final required = (schema['required'] as List).cast<String>();
      final properties = (schema['properties'] as Map).cast<String, Object?>();

      final services = [
        _service(),
        _service(
          serviceId: 'svc_ikeja',
          collectingBody: 'Ikeja Electric',
          knownAmount: null,
        ),
      ];
      final context = {
        'services': [for (final service in services) service.toJson()],
      };

      final rows = (context['services'] as List).cast<Map<String, dynamic>>();
      expect(rows, hasLength(2));
      for (final row in rows) {
        for (final field in required) {
          expect(
            row.containsKey(field),
            isTrue,
            reason: 'ServiceResultRow requires $field',
          );
        }
        // Every emitted key is one the schema defines, so the agent's
        // pre-send validation accepts the row rather than falling back.
        for (final key in row.keys) {
          expect(
            properties.containsKey(key),
            isTrue,
            reason: '$key is not a ServiceResultRow field',
          );
        }
      }
    });
  });

  group('ServiceSummary.fromJson', () {
    test('reads the camelCase wire shape', () {
      final service = ServiceSummary.fromJson({
        'serviceId': 'svc_lagos',
        'name': 'Land Use Charge',
        'collectingBody': 'Lagos State Government',
        'category': 'Government',
        'knownAmount': 2500000,
        'currency': 'NGN',
        'status': 'active',
        'confidence': 0.9,
      });
      expect(service.serviceId, 'svc_lagos');
      expect(service.collectingBody, 'Lagos State Government');
      expect(service.knownAmount, 2500000);
    });

    test('still tolerates the former snake_case shape', () {
      final service = ServiceSummary.fromJson({
        'service_id': 'svc_lagos',
        'name': 'Land Use Charge',
        'collecting_body': 'Lagos State Government',
        'category': 'Government',
        'known_amount': 2500000,
      });
      expect(service.serviceId, 'svc_lagos');
      expect(service.collectingBody, 'Lagos State Government');
      expect(service.knownAmount, 2500000);
    });

    test('is a fixed point for toJson', () {
      final original = _service(knownAmount: null);
      final roundTripped = ServiceSummary.fromJson(original.toJson());
      expect(roundTripped.toJson(), original.toJson());
    });
  });
}
