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

    test('each document component schema mirrors its item schema', () {
      final document =
          (SabiCatalog.document()['components'] as Map).cast<String, Object?>();
      for (final item in sabiCatalog.items) {
        final docSchema = (document[item.name] as Map).cast<String, Object?>();
        final docProps =
            ((docSchema['properties'] as Map?) ?? const {}).keys.toSet();
        final itemProps =
            (((item.dataSchema.value['properties'] as Map?) ?? const {}).keys
                  .toSet()
                ..remove('component'));
        expect(
          docProps,
          equals(itemProps),
          reason: '${item.name} properties drifted from the published catalog',
        );
      }
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
              as Map)['catalogId'] = 'https://other.example/catalog.json';
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

    testWidgets('routes a catalog component action to the host', (tester) async {
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
  });
}
