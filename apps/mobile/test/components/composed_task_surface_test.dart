import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/composed_task_surface.dart';
import 'package:sabi_mobile/models/composed_surface.dart';

import '../helpers.dart';

void main() {
  testWidgets('renders a catalogue component natively', (tester) async {
    const surface = ComposedSurface(
      surfaceId: 's1',
      task: SurfaceTask.confirmation,
      components: [
        SurfaceComponent(
          type: 'confirmationSummary',
          data: {
            'amount': 2500000,
            'currency': 'NGN',
            'payee': 'Lagos State Government',
            'reference': 'LUC-2026-0001',
          },
        ),
      ],
    );
    await pumpSab(
      tester,
      const Scaffold(body: ComposedTaskSurface(surface: surface)),
    );
    expect(find.text('Lagos State Government'), findsOneWidget);
    expect(find.text('LUC-2026-0001'), findsOneWidget);
    expect(find.textContaining('25,000'), findsOneWidget);
  });

  testWidgets('refuses an unknown component and renders the fallback form', (
    tester,
  ) async {
    const surface = ComposedSurface(
      surfaceId: 's2',
      task: SurfaceTask.confirmation,
      components: [SurfaceComponent(type: 'mysteryWidget')],
    );
    await pumpSab(
      tester,
      const Scaffold(body: ComposedTaskSurface(surface: surface)),
    );
    expect(find.textContaining('we don’t recognise'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    expect(find.text('Continue'), findsOneWidget);
  });

  testWidgets('a surface with no recognised task falls back too', (
    tester,
  ) async {
    const surface = ComposedSurface(
      surfaceId: 's3',
      components: [
        SurfaceComponent(type: 'text', data: {'text': 'hi'}),
      ],
    );
    await pumpSab(
      tester,
      const Scaffold(body: ComposedTaskSurface(surface: surface)),
    );
    expect(find.text('hi'), findsNothing);
    expect(find.byType(TextField), findsOneWidget);
  });

  group('C-012 parsing', () {
    test('reads the declarative stream and discards unknown messages', () {
      final surface = ComposedSurface.parse({
        'messages': [
          {'type': 'createSurface', 'surfaceId': 's1', 'task': 'confirmation'},
          {'type': 'somethingNew', 'surfaceId': 's1'},
          {
            'type': 'updateComponents',
            'surfaceId': 's1',
            'components': [
              {
                'type': 'text',
                'data': {'text': 'Confirm your payment'},
              },
            ],
          },
          {
            'type': 'updateDataModel',
            'surfaceId': 's1',
            'data': {'reference': 'REF-1'},
          },
        ],
        'fallback': 'confirmation',
      });
      expect(surface, isNotNull);
      expect(surface!.task, SurfaceTask.confirmation);
      expect(surface.components, hasLength(1));
      expect(surface.data['reference'], 'REF-1');
      expect(surface.fallback, 'confirmation');
    });

    test('unknown task yields a null task so the fallback can run', () {
      final surface = ComposedSurface.parse({
        'messages': [
          {'type': 'createSurface', 'surfaceId': 's1', 'task': 'teleport'},
        ],
      });
      expect(surface!.task, isNull);
    });

    test('isRenderable rejects a component outside the catalogue', () {
      const surface = ComposedSurface(
        surfaceId: 's1',
        task: SurfaceTask.discovery,
        components: [SurfaceComponent(type: 'mysteryWidget')],
      );
      expect(surface.isRenderable(SabComponentCatalogue.types), isFalse);
    });
  });
}
