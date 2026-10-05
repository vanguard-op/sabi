import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/a2ui/mock_surface_repository.dart';
import 'package:sabi_mobile/a2ui/providers.dart';
import 'package:sabi_mobile/a2ui/surface_repository.dart';
import 'package:sabi_mobile/a2ui/surface_task.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/case/case_controller.dart';
import 'package:sabi_mobile/features/case/case_task_view.dart';
import 'package:sabi_mobile/features/home/home_controller.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/intent_result.dart';
import 'package:sabi_mobile/models/payment_case.dart';

import '../../helpers.dart';

/// A catalogue whose settled intent is a recovery task bound to a case, so the
/// inline recovery path is reached deterministically.
class _RecoveryCatalogue implements CatalogueRepository {
  _RecoveryCatalogue(this.intent);

  final IntentResult intent;

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  }) async => intent;

  @override
  Future<CatalogueSearchResult> search(String query) async =>
      const CatalogueSearchResult(results: [], noMatch: true);

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async =>
      throw const ServiceNotFoundException();
}

/// A catalogue that resolves a record lookup, so the case record renders inline.
class _RecordCatalogue implements CatalogueRepository {
  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  }) async => const IntentResult(intentType: 'receipt_lookup', confidence: 0.9);

  @override
  Future<CatalogueSearchResult> search(String query) async =>
      const CatalogueSearchResult(results: [], noMatch: true);

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async =>
      throw const ServiceNotFoundException();
}

/// A record lookup double that resolves the case the caller scripts.
class _ScriptedRecordLookup implements RecordLookupRepository {
  _ScriptedRecordLookup(this.records);

  final List<ResolvedRecord> records;

  @override
  Future<List<ResolvedRecord>> lookup(String query, {int limit = 5}) async =>
      records;
}

/// A surface repository that never composes, so the client's prewritten shell
/// for the same task is exercised.
class _NoCompositionSurface implements SurfaceRepository {
  @override
  Future<Map<String, dynamic>> compose(SurfaceRequest request) async => {
    'messages': const <Map<String, dynamic>>[],
    'fallback': request.task.wire,
  };
}

IntentResult _recoveryIntent({String caseId = 'case_1'}) => IntentResult(
  intentType: 'status_check',
  confidence: 0.9,
  constraints: {'task': 'recovery', 'caseId': caseId, 'status': 'failed'},
);

ResolvedRecord _caseRecord(
  String caseId, {
  String paymentId = 'pay_failed_1',
}) => ResolvedRecord(
  kind: 'case',
  id: caseId,
  caseSummary: CaseSummary(
    caseId: caseId,
    paymentId: paymentId,
    type: CaseType.failedNoDelivery,
    status: CaseStatus.awaitingProvider,
    openedAt: DateTime.utc(2026, 9, 29, 11, 0),
    updatedAt: DateTime.utc(2026, 9, 30, 9, 0),
  ),
);

List<Override> _overrides({
  required CatalogueRepository catalogue,
  RecordLookupRepository? recordLookup,
  MockCasesRepository? cases,
  SurfaceRepository? surface,
}) => [
  catalogueRepositoryProvider.overrideWith((ref) => catalogue),
  receiptRepositoryProvider.overrideWith(
    (ref) => MockReceiptRepository(receipts: const []),
  ),
  surfaceRepositoryProvider.overrideWith(
    (ref) => surface ?? MockSurfaceRepository(latency: Duration.zero),
  ),
  casesRepositoryProvider.overrideWith(
    (ref) => cases ?? MockCasesRepository(latency: Duration.zero),
  ),
  if (recordLookup != null)
    recordLookupRepositoryProvider.overrideWith((ref) => recordLookup),
];

final Finder _sendButton = find.ancestor(
  of: find.byTooltip('Send'),
  matching: find.byType(IconButton),
);

Future<void> _submitRequest(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField).first, text);
  await tester.pump();
  await tester.tap(_sendButton);
  await tester.pumpAndSettle();
}

/// Taps an action in the inline task, scrolling it into view first: the
/// conversation grows past the test viewport, so the action is not always
/// visible without scrolling.
Future<void> _tapAction(WidgetTester tester, String label) async {
  final action = find.text(label);
  await tester.ensureVisible(action);
  await tester.pumpAndSettle();
  await tester.tap(action);
  await tester.pumpAndSettle();
}

void main() {
  group('recovery completes inline in the conversation', () {
    testWidgets('a recovery task renders the state and refunds inline', (
      tester,
    ) async {
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(catalogue: _RecoveryCatalogue(_recoveryIntent())),
      );
      await tester.pumpAndSettle();
      await _submitRequest(tester, 'my payment failed');

      // The conversation holds the recovery state: the composed surface frames
      // it and the shared case shell drives the same task inline.
      expect(
        containerOf(tester).read(homeControllerProvider).phase,
        HomePhase.recovering,
      );
      expect(containerOf(tester).read(homeControllerProvider).caseId, 'case_1');
      expect(find.byType(CaseTaskView), findsOneWidget);
      expect(find.text(SabStrings.english.recoveringTitle), findsOneWidget);
      // The Case screen stays reachable as the alternate route.
      expect(find.text(SabStrings.english.openCase), findsOneWidget);

      // The refund is the C-029 call and completes in the conversation.
      await _tapAction(tester, SabStrings.english.caseStartRefund);
      expect(
        containerOf(tester).read(caseControllerProvider('case_1')).phase,
        CasePhase.refunded,
      );
      expect(find.text(SabStrings.english.caseRefundSubmitted), findsOneWidget);
    });

    testWidgets('a case record lookup completes recovery inline', (
      tester,
    ) async {
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(
          catalogue: _RecordCatalogue(),
          recordLookup: _ScriptedRecordLookup([_caseRecord('case_1')]),
        ),
      );
      await tester.pumpAndSettle();
      await _submitRequest(tester, 'did my Ikeja payment go through');

      // A resolved case renders its recovery surface and the inline task, so
      // the refund completes in the conversation (user-flow Flow 9).
      expect(
        containerOf(tester).read(homeControllerProvider).phase,
        HomePhase.record,
      );
      expect(containerOf(tester).read(homeControllerProvider).caseId, 'case_1');
      expect(find.byType(CaseTaskView), findsOneWidget);
      expect(find.text(SabStrings.english.caseStartRefund), findsOneWidget);
      expect(find.text(SabStrings.english.openCase), findsOneWidget);

      await _tapAction(tester, SabStrings.english.caseStartRefund);
      expect(
        containerOf(tester).read(caseControllerProvider('case_1')).phase,
        CasePhase.refunded,
      );
    });

    testWidgets('a failed composition still renders the prewritten shell', (
      tester,
    ) async {
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(
          catalogue: _RecoveryCatalogue(_recoveryIntent()),
          surface: _NoCompositionSurface(),
        ),
      );
      await tester.pumpAndSettle();
      await _submitRequest(tester, 'my payment failed');

      // The task stays completable: the client's own shell carries it when the
      // agent composes nothing, and the screen stays reachable.
      expect(find.byType(CaseTaskView), findsOneWidget);
      expect(find.text(SabStrings.english.caseStartRefund), findsOneWidget);
      expect(find.text(SabStrings.english.openCase), findsOneWidget);
    });

    testWidgets('a duplicate refund is reported inline, not swallowed', (
      tester,
    ) async {
      final cases = MockCasesRepository(latency: Duration.zero)
        ..failNextRefund = true;
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(
          catalogue: _RecoveryCatalogue(_recoveryIntent()),
          cases: cases,
        ),
      );
      await tester.pumpAndSettle();
      await _submitRequest(tester, 'my payment failed');

      await _tapAction(tester, SabStrings.english.caseStartRefund);
      expect(find.text(SabStrings.english.caseRefundBlocked), findsOneWidget);
    });

    testWidgets('an escalated case raises a dispute inline', (tester) async {
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(
          catalogue: _RecoveryCatalogue(_recoveryIntent(caseId: 'case_4')),
        ),
      );
      await tester.pumpAndSettle();
      await _submitRequest(tester, 'my payment failed');

      // case_4 is escalated: the dispute action is offered, not the refund.
      expect(find.text(SabStrings.english.raiseDispute), findsOneWidget);
      expect(find.text(SabStrings.english.caseStartRefund), findsNothing);

      await _tapAction(tester, SabStrings.english.raiseDispute);
      expect(
        containerOf(tester).read(caseControllerProvider('case_4')).phase,
        CasePhase.disputed,
      );
      expect(
        find.text(SabStrings.english.caseDisputeSubmitted),
        findsOneWidget,
      );
    });

    testWidgets('offline blocks the recovery action inline', (tester) async {
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(catalogue: _RecoveryCatalogue(_recoveryIntent())),
      );
      await tester.pumpAndSettle();
      await _submitRequest(tester, 'my payment failed');

      containerOf(tester).read(connectivityProvider.notifier).setOnline(false);
      await tester.pumpAndSettle();

      expect(find.text(SabStrings.english.caseStartRefund), findsNothing);
      expect(
        containerOf(tester).read(caseControllerProvider('case_1')).canRefund,
        isFalse,
      );
    });

    testWidgets('a recovery task with no case renders the surface alone', (
      tester,
    ) async {
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(
          catalogue: _RecoveryCatalogue(
            const IntentResult(
              intentType: 'status_check',
              confidence: 0.9,
              constraints: {'task': 'recovery', 'status': 'failed'},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await _submitRequest(tester, 'something went wrong');

      // No case is bound: the state still shows, with no inline task invented.
      expect(
        containerOf(tester).read(homeControllerProvider).phase,
        HomePhase.recovering,
      );
      expect(
        containerOf(tester).read(homeControllerProvider).surfaceTask,
        SurfaceTask.recovery,
      );
      expect(find.byType(CaseTaskView), findsNothing);
    });
  });
}
