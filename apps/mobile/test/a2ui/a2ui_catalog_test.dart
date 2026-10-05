import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/a2ui/a2ui_surface.dart';
import 'package:sabi_mobile/a2ui/sabi_catalog.dart';

import '../helpers.dart';

/// A well-formed confirmation stream against the published catalog.
Map<String, dynamic> _confirmationBody() => {
  'messages': [
    {
      'version': 'v0.9',
      'createSurface': {
        'surfaceId': 'confirmation_1',
        'catalogId': SabiCatalog.catalogId,
      },
    },
    {
      'version': 'v0.9',
      'updateComponents': {
        'surfaceId': 'confirmation_1',
        'components': [
          {
            'id': 'root',
            'component': 'ConfirmationSummary',
            'amount': 2500000,
            'currency': 'NGN',
            'payee': 'Lagos State Government',
            'reference': 'LUC-2026-0001',
          },
        ],
      },
    },
  ],
  'task': 'confirmation',
  'fallback': 'confirmation',
};

/// Resolves a local `$ref` such as `#/components/ServiceResultRow` against the
/// published document, so a component another component references can be
/// compared to the runtime schema that inlines it.
Map<String, Object?> _resolveDocumentRef(
  Map<String, Object?> document,
  Map<String, Object?> schema,
) {
  final ref = schema[r'$ref'];
  if (ref is! String || !ref.startsWith('#/')) return schema;
  Object? node = document;
  for (final segment in ref.substring(2).split('/')) {
    node = (node as Map)[segment];
  }
  return (node as Map).cast<String, Object?>();
}

/// Asserts the runtime [itemSchema] declares the same property names, required
/// sets, and scalar types as the published [documentSchema], recursively through
/// nested object properties and array items.
///
/// The renderer validates against the runtime items, so this is the guard that
/// keeps them from drifting from the authored document. The type set is
/// compared because a document-valid `null` on an optional field was refused by
/// a non-nullable runtime type and silently fell back; comparing `type` keeps
/// the nullability in step too.
void _expectSchemaAgrees(
  Map<String, Object?> document, {
  required String where,
  required Map<String, Object?> documentSchema,
  required Map<String, Object?> itemSchema,
}) {
  final doc = _resolveDocumentRef(document, documentSchema);

  final docTypes = _typeNames(doc);
  final itemTypes = _typeNames(itemSchema);
  if (docTypes != null && itemTypes != null) {
    expect(itemTypes, equals(docTypes), reason: '$where: type');
  }

  final docProperties = (doc['properties'] as Map?) ?? const {};
  final itemProperties = (itemSchema['properties'] as Map?) ?? const {};

  if (docProperties.isNotEmpty || itemProperties.isNotEmpty) {
    final docNames = docProperties.keys.cast<String>().toSet();
    // `component` is the discriminator the renderer injects; the document names
    // components but does not declare the property.
    final itemNames = itemProperties.keys.cast<String>().toSet()
      ..remove('component');
    expect(itemNames, equals(docNames), reason: '$where: property names');

    final docRequired = ((doc['required'] as List?) ?? const [])
        .cast<String>()
        .toSet();
    final itemRequired =
        ((itemSchema['required'] as List?) ?? const []).cast<String>().toSet()
          ..remove('component');
    expect(
      itemRequired,
      equals(docRequired),
      reason: '$where: required fields',
    );

    for (final name in docNames) {
      final docChild = docProperties[name];
      final itemChild = itemProperties[name];
      if (docChild is! Map || itemChild is! Map) continue;
      _expectSchemaAgrees(
        document,
        where: '$where.$name',
        documentSchema: docChild.cast<String, Object?>(),
        itemSchema: itemChild.cast<String, Object?>(),
      );
    }
  }

  final docItems = (doc['items'] as Map?)?.cast<String, Object?>();
  final itemItems = (itemSchema['items'] as Map?)?.cast<String, Object?>();
  if (docItems != null || itemItems != null) {
    expect(
      docItems != null && itemItems != null,
      isTrue,
      reason: '$where: array items declared on only one side',
    );
    _expectSchemaAgrees(
      document,
      where: '$where[]',
      documentSchema: docItems!,
      itemSchema: itemItems!,
    );
  }
}

/// The JSON Schema `type` of [schema] as a set of type names, or null when the
/// schema declares none (a `$ref` before resolution).
Set<String>? _typeNames(Map<String, Object?> schema) {
  final type = schema['type'];
  if (type is String) return {type};
  if (type is List) return type.map((t) => t.toString()).toSet();
  return null;
}

void main() {
  group('the published Sabi catalog', () {
    test('carries the catalogId as both catalogId and \$id', () {
      final doc = SabiCatalog.document();
      expect(doc['\$id'], SabiCatalog.catalogId);
      expect(doc['catalogId'], SabiCatalog.catalogId);
      expect(SabiCatalog.catalogId, startsWith('https://'));
    });

    test('covers the composed surfaces and not the shell', () {
      for (final name in [
        'ConfirmationSummary',
        'AmountEntry',
        'ProviderPicker',
        'ServiceResultRow',
        'ReceiptCard',
        'StatusPill',
        'Verification',
        'Recovery',
      ]) {
        expect(SabiCatalog.defines(name), isTrue, reason: name);
      }
      for (final shell in [
        'NavigationShell',
        'ComposedTaskSurface',
        'EmptyState',
        'OfflineBanner',
        'SuccessToast',
        'ErrorState',
      ]) {
        expect(SabiCatalog.defines(shell), isFalse, reason: shell);
      }
    });

    test('advertises the catalog through supportedCatalogIds', () {
      expect(sabiSupportedCatalogIds, contains(SabiCatalog.catalogId));
    });

    test('the document components mirror the renderer items', () {
      final documentComponents = (SabiCatalog.document()['components'] as Map)
          .keys
          .cast<String>()
          .toSet();
      final itemNames = sabiCatalog.items.map((i) => i.name).toSet();
      expect(itemNames, equals(documentComponents));
    });

    test('every item schema agrees with the published document', () {
      // The runtime `CatalogItem` schemas are a third copy of the catalog: the
      // document is generated to the server JSON, but the renderer validates
      // against its own items. Compare every component, recursively through
      // nested objects and array items, on what decides what the renderer
      // accepts: declared property names, required sets, and scalar types.
      final catalog = SabiCatalog.document();
      final components = (catalog['components'] as Map).cast<String, Object?>();
      for (final item in sabiCatalog.items) {
        final docSchema = (components[item.name] as Map)
            .cast<String, Object?>();
        _expectSchemaAgrees(
          catalog,
          where: item.name,
          documentSchema: docSchema,
          itemSchema: item.dataSchema.value,
        );
      }
    });

    test('the ProviderPicker services item matches ServiceResultRow', () {
      final catalog = SabiCatalog.document();
      final document = (catalog['components'] as Map).cast<String, Object?>();
      final picker = (document['ProviderPicker'] as Map)
          .cast<String, Object?>();
      final services =
          (picker['properties'] as Map)['services'] as Map<String, Object?>;
      final items = services['items'] as Map<String, Object?>;

      // The document references the row by `$ref`; resolving it proves the
      // picker's nested schema is the row, not an unconstrained object.
      final resolved = _resolveDocumentRef(catalog, items);
      expect(
        ((resolved['properties'] as Map).keys.toSet()),
        containsAll(['serviceId', 'collectingBody', 'category']),
      );
      expect(((resolved['required'] as List).cast<String>().toSet()), {
        'serviceId',
        'collectingBody',
        'category',
      });

      final item = sabiCatalog.items.firstWhere(
        (i) => i.name == SabiCatalog.providerPicker.value,
      );
      final runtimeServices =
          ((item.dataSchema.value['properties'] as Map)['services']
              as Map<String, Object?>);
      final runtimeItems = runtimeServices['items'] as Map<String, Object?>;
      expect(((runtimeItems['required'] as List).cast<String>().toSet()), {
        'serviceId',
        'collectingBody',
        'category',
      });
    });
  });

  group('A2uiGate (client-side phase-2 validation)', () {
    test('accepts a catalog-conforming stream', () {
      final stream = A2uiGate.gate(
        _confirmationBody(),
        defines: SabiCatalog.defines,
      );
      expect(stream.surfaceId, 'confirmation_1');
      expect(stream.task, 'confirmation');
      expect(stream.messages, hasLength(2));
    });

    test('rejects an unknown component', () {
      final body = _confirmationBody();
      (((body['messages'] as List)[1] as Map)['updateComponents']
          as Map)['components'] = [
        {'id': 'root', 'component': 'MysteryWidget'},
      ];
      expect(
        () => A2uiGate.gate(body, defines: SabiCatalog.defines),
        throwsA(
          isA<A2uiGateException>().having(
            (e) => e.message,
            'message',
            contains('not in the published catalog'),
          ),
        ),
      );
    });

    test('rejects a surface naming another catalog', () {
      final body = _confirmationBody();
      (((body['messages'] as List)[0] as Map)['createSurface']
              as Map)['catalogId'] =
          'https://other.example/catalog.json';
      expect(
        () => A2uiGate.gate(body, defines: SabiCatalog.defines),
        throwsA(isA<A2uiGateException>()),
      );
    });

    test('rejects a surface with no root component', () {
      final body = _confirmationBody();
      (((body['messages'] as List)[1] as Map)['updateComponents']
          as Map)['components'] = [
        {
          'id': 'not_root',
          'component': 'ConfirmationSummary',
          'amount': 1,
          'payee': 'x',
        },
      ];
      expect(
        () => A2uiGate.gate(body, defines: SabiCatalog.defines),
        throwsA(
          isA<A2uiGateException>().having(
            (e) => e.message,
            'message',
            contains('root'),
          ),
        ),
      );
    });

    test('rejects a malformed message (bad version)', () {
      final body = _confirmationBody();
      ((body['messages'] as List)[0] as Map)['version'] = 'v0.8';
      expect(
        () => A2uiGate.gate(body, defines: SabiCatalog.defines),
        throwsA(isA<A2uiGateException>()),
      );
    });

    test('rejects a body with no messages array', () {
      expect(
        () => A2uiGate.gate(const {}, defines: SabiCatalog.defines),
        throwsA(isA<A2uiGateException>()),
      );
    });
  });

  group('A2uiSurfaceView', () {
    testWidgets('renders a gated stream through the GenUI SDK', (tester) async {
      final stream = A2uiGate.gate(
        _confirmationBody(),
        defines: SabiCatalog.defines,
      );
      await pumpSab(
        tester,
        Scaffold(
          body: A2uiSurfaceView(
            stream: stream,
            fallback: (context) => const Text('FALLBACK'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Lagos State Government'), findsOneWidget);
      expect(find.textContaining('25,000'), findsOneWidget);
      expect(find.text('FALLBACK'), findsNothing);
    });

    testWidgets('renders the fallback when the stream is null', (tester) async {
      await pumpSab(
        tester,
        Scaffold(
          body: A2uiSurfaceView(
            stream: null,
            fallback: (context) => const Text('FALLBACK'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('FALLBACK'), findsOneWidget);
    });

    testWidgets('reports VALIDATION_FAILED and falls back', (tester) async {
      // A component whose required properties are absent passes the name gate
      // but fails the SDK's catalog schema validation, so the client reports it
      // and renders the fallback for the same task.
      final body = _confirmationBody();
      (((body['messages'] as List)[1] as Map)['updateComponents']
          as Map)['components'] = [
        {'id': 'root', 'component': 'ConfirmationSummary'},
      ];
      final stream = A2uiGate.gate(body, defines: SabiCatalog.defines);
      Map<String, Object?>? reported;
      await pumpSab(
        tester,
        Scaffold(
          body: A2uiSurfaceView(
            stream: stream,
            fallback: (context) => const Text('FALLBACK'),
            onValidationFailed: (error) => reported = error,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(reported?['code'], 'VALIDATION_FAILED');
      expect(find.text('FALLBACK'), findsOneWidget);
    });

    testWidgets('routes a catalog component action to the host', (
      tester,
    ) async {
      final stream = A2uiGate.gate({
        'messages': [
          {
            'version': 'v0.9',
            'createSurface': {
              'surfaceId': 'd1',
              'catalogId': SabiCatalog.catalogId,
            },
          },
          {
            'version': 'v0.9',
            'updateComponents': {
              'surfaceId': 'd1',
              'components': [
                {
                  'id': 'root',
                  'component': 'ServiceResultRow',
                  'serviceId': 'svc_lagos',
                  'name': 'Land Use Charge',
                  'collectingBody': 'Lagos State Government',
                  'category': 'Government',
                },
              ],
            },
          },
        ],
        'task': 'discovery',
        'fallback': 'discovery',
      }, defines: SabiCatalog.defines);
      A2uiAction? dispatched;
      await pumpSab(
        tester,
        Scaffold(
          body: A2uiSurfaceView(
            stream: stream,
            onAction: (action) => dispatched = action,
            fallback: (context) => const Text('FALLBACK'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Lagos State Government'));
      await tester.pumpAndSettle();
      expect(dispatched?.name, SabiActions.selectService);
      expect(dispatched?.context['serviceId'], 'svc_lagos');
    });

    testWidgets('renders one row per well-formed ProviderPicker service', (
      tester,
    ) async {
      final stream = A2uiGate.gate({
        'messages': [
          {
            'version': 'v0.9',
            'createSurface': {
              'surfaceId': 'd2',
              'catalogId': SabiCatalog.catalogId,
            },
          },
          {
            'version': 'v0.9',
            'updateComponents': {
              'surfaceId': 'd2',
              'components': [
                {
                  'id': 'root',
                  'component': 'ProviderPicker',
                  'services': [
                    {
                      'serviceId': 'svc_lagos',
                      'name': 'Land Use Charge',
                      'collectingBody': 'Lagos State Government',
                      'category': 'Government',
                    },
                    {
                      'serviceId': 'svc_ikeja',
                      'name': 'Electricity',
                      'collectingBody': 'Ikeja Electric',
                      'category': 'Utilities',
                      // The document admits null here; the row must render the
                      // "amount confirmed at payment" line, not fall back.
                      'knownAmount': null,
                    },
                  ],
                },
              ],
            },
          },
        ],
        'task': 'discovery',
        'fallback': 'discovery',
      }, defines: SabiCatalog.defines);
      await pumpSab(
        tester,
        Scaffold(
          body: A2uiSurfaceView(
            stream: stream,
            fallback: (context) => const Text('FALLBACK'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Lagos State Government'), findsOneWidget);
      expect(find.text('Ikeja Electric'), findsOneWidget);
      expect(find.text('FALLBACK'), findsNothing);
    });

    testWidgets('refuses an empty ProviderPicker service and falls back', (
      tester,
    ) async {
      // The picker's `services` entries are ServiceResultRow-shaped, so an
      // entry missing the required fields must fail validation rather than
      // render a blank row.
      final Map<String, dynamic> body = {
        'messages': [
          {
            'version': 'v0.9',
            'createSurface': {
              'surfaceId': 'd3',
              'catalogId': SabiCatalog.catalogId,
            },
          },
          {
            'version': 'v0.9',
            'updateComponents': {
              'surfaceId': 'd3',
              'components': [
                {
                  'id': 'root',
                  'component': 'ProviderPicker',
                  'services': [<String, Object?>{}],
                },
              ],
            },
          },
        ],
        'task': 'discovery',
        'fallback': 'discovery',
      };
      final stream = A2uiGate.gate(body, defines: SabiCatalog.defines);
      Map<String, Object?>? reported;
      await pumpSab(
        tester,
        Scaffold(
          body: A2uiSurfaceView(
            stream: stream,
            fallback: (context) => const Text('FALLBACK'),
            onValidationFailed: (error) => reported = error,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(reported?['code'], 'VALIDATION_FAILED');
      expect(find.text('FALLBACK'), findsOneWidget);
    });
  });
}
