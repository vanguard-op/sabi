import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/a2ui/mock_surface_repository.dart';
import 'package:sabi_mobile/a2ui/providers.dart';
import 'package:sabi_mobile/a2ui/surface_task.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/home/home_controller.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/features/payment/payment_strings.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/intent_result.dart';
import 'package:sabi_mobile/models/receipt_summary.dart';
import 'package:sabi_mobile/models/service_summary.dart';

import '../../helpers.dart';

/// A catalogue double whose intent results are scripted per call. The task
/// surfaces are reached from the intent's explicit `task` constraint and the
/// record lookup from the `receipt_lookup` intent type, so both are exercisable.
class _ScriptedCatalogue implements CatalogueRepository {
  _ScriptedCatalogue({required this.intents, this.searchResults = const []});

  final List<IntentResult> intents;
  final List<ServiceSummary> searchResults;
  int intentCalls = 0;

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  }) async {
    final index = intentCalls < intents.length
        ? intentCalls
        : intents.length - 1;
    intentCalls++;
    return intents[index];
  }

  @override
  Future<CatalogueSearchResult> search(String query) async =>
      CatalogueSearchResult(
        results: searchResults,
        noMatch: searchResults.isEmpty,
      );

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async =>
      throw const ServiceNotFoundException();
}

/// A record lookup double: the caller scripts the records it resolves, so the
/// inline render and the empty answer can both be asserted.
class _ScriptedRecordLookup implements RecordLookupRepository {
  _ScriptedRecordLookup(this.records);

  final List<ResolvedRecord> records;
  int calls = 0;

  @override
  Future<List<ResolvedRecord>> lookup(String query, {int limit = 5}) async {
    calls++;
    return records;
  }
}

ServiceSummary _service(String id, String body, {int? amount}) => ServiceSummary(
  serviceId: id,
  name: 'Land Use Charge',
  collectingBody: body,
  category: 'Government',
  knownAmount: amount,
  confidence: 0.9,
);

ReceiptSummary _receipt() => ReceiptSummary(
  id: 'rcp_1',
  reference: 'LUC-2026-0001',
  payee: 'Lagos State Government',
  amount: 2500000,
  currency: 'NGN',
  issuedAt: DateTime.utc(2026, 9, 28, 10, 30),
  kind: 'Official receipt',
  status: PaymentStatus.settled,
);

IntentResult _task(String task, {ServiceSummary? service, int? amount}) =>
    IntentResult(
      intentType: 'bill_payment',
      target: service?.collectingBody,
      amount: amount,
      reference: 'LUC-2026-0001',
      confidence: 0.9,
      constraints: {'task': task},
      candidates: service == null ? const [] : [service],
    );

ProviderContainer _container({
  required CatalogueRepository catalogue,
  RecordLookupRepository? recordLookup,
}) {
  final container = ProviderContainer(
    overrides: [
      catalogueRepositoryProvider.overrideWith((ref) => catalogue),
      surfaceRepositoryProvider.overrideWith(
        (ref) => MockSurfaceRepository(latency: Duration.zero),
      ),
      if (recordLookup != null)
        recordLookupRepositoryProvider.overrideWith((ref) => recordLookup),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

final Finder _sendButton = find.ancestor(
  of: find.byTooltip('Send'),
  matching: find.byType(IconButton),
);

Future<void> _submit(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(_sendButton);
  await tester.pumpAndSettle();
}

void main() {
  group('task-shaped intents compose inline', () {
    test('a confirmation task selects the resolved service', () async {
      final catalogue = _ScriptedCatalogue(
        intents: [
          _task(
            'confirmation',
            service: _service('svc_lagos', 'Lagos State Government', amount: 2500000),
            amount: 2500000,
          ),
        ],
      );
      final container = _container(catalogue: catalogue);
      await container.read(homeControllerProvider.notifier).submit('pay land use');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.confirmation);
      expect(state.selectedService?.serviceId, 'svc_lagos');
      expect(state.turns.single.surfaceTask, SurfaceTask.confirmation);
    });

    test('a verification task holds the payment, not fails it', () async {
      final catalogue = _ScriptedCatalogue(
        intents: [_task('verification')],
      );
      final container = _container(catalogue: catalogue);
      await container.read(homeControllerProvider.notifier).submit('pay land use');
      expect(container.read(homeControllerProvider).phase, HomePhase.verifying);
    });

    test('a recovery task composes the recovery surface', () async {
      final catalogue = _ScriptedCatalogue(intents: [_task('recovery')]);
      final container = _container(catalogue: catalogue);
      await container.read(homeControllerProvider.notifier).submit('my payment failed');
      expect(container.read(homeControllerProvider).phase, HomePhase.recovering);
    });

    test('a plain resolved payment still reaches discovery, not forced inline', () async {
      // Without an explicit task the request keeps the discovery path, so the
      // payment screen remains an equal route and neither path is the fallback
      // for the other (D-050, screens.md "dual path").
      final catalogue = _ScriptedCatalogue(
        intents: [
          IntentResult(
            intentType: 'bill_payment',
            target: 'Lagos State Government',
            confidence: 0.9,
            candidates: [_service('svc_lagos', 'Lagos State Government')],
          ),
        ],
      );
      final container = _container(catalogue: catalogue);
      await container.read(homeControllerProvider.notifier).submit('pay land use');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.discovery);
      expect(state.selectedService, isNull);
      expect(state.candidates, hasLength(1));
    });

    test('a task-shaped request composes inline without a search first', () async {
      final catalogue = _ScriptedCatalogue(
        intents: [_task('verification')],
        searchResults: [_service('svc_x', 'Somewhere Council')],
      );
      final container = _container(catalogue: catalogue);
      await container.read(homeControllerProvider.notifier).submit('verify me');
      // The inline task is the first-class route: it does not fall back to a
      // catalogue search to reach the screen.
      expect(container.read(homeControllerProvider).phase, HomePhase.verifying);
    });
  });

  group('record lookup', () {
    test('a single match renders inline with the record', () async {
      final catalogue = _ScriptedCatalogue(
        intents: const [
          IntentResult(intentType: 'receipt_lookup', confidence: 0.9),
        ],
      );
      final lookup = _ScriptedRecordLookup([
        ResolvedRecord(kind: 'receipt', id: 'rcp_1', receipt: _receipt()),
      ]);
      final container = _container(catalogue: catalogue, recordLookup: lookup);
      await container
          .read(homeControllerProvider.notifier)
          .submit('show me my December NEPA receipt');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.record);
      expect(state.record?.id, 'rcp_1');
      expect(state.records, hasLength(1));
      expect(lookup.calls, 1);
    });

    test('several matches present candidates instead of guessing', () async {
      final catalogue = _ScriptedCatalogue(
        intents: const [
          IntentResult(intentType: 'receipt_lookup', confidence: 0.9),
        ],
      );
      final lookup = _ScriptedRecordLookup([
        ResolvedRecord(kind: 'receipt', id: 'rcp_1', receipt: _receipt()),
        ResolvedRecord(
          kind: 'receipt',
          id: 'rcp_2',
          receipt: ReceiptSummary(
            id: 'rcp_2',
            reference: 'MTN-2026-4410',
            payee: 'MTN Nigeria',
            amount: 200000,
            currency: 'NGN',
            issuedAt: DateTime.utc(2026, 9, 26),
            kind: 'Biller confirmation',
            status: PaymentStatus.pending,
          ),
        ),
      ]);
      final container = _container(catalogue: catalogue, recordLookup: lookup);
      await container.read(homeControllerProvider.notifier).submit('receipts');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.record);
      expect(state.record, isNull);
      expect(state.records, hasLength(2));
    });

    test('no match states it plainly and composes no record', () async {
      final catalogue = _ScriptedCatalogue(
        intents: const [
          IntentResult(intentType: 'receipt_lookup', confidence: 0.9),
        ],
      );
      final container = _container(
        catalogue: catalogue,
        recordLookup: _ScriptedRecordLookup(const []),
      );
      await container
          .read(homeControllerProvider.notifier)
          .submit('receipt for nothing');
      final state = container.read(homeControllerProvider);
      expect(state.phase, HomePhase.noRecord);
      expect(state.record, isNull);
      expect(state.records, isEmpty);
    });

    test('a lookup failure resolves to the error state, not a fake record', () async {
      final catalogue = _ScriptedCatalogue(
        intents: const [
          IntentResult(intentType: 'receipt_lookup', confidence: 0.9),
        ],
      );
      final container = _container(
        catalogue: catalogue,
        recordLookup: _ThrowingRecordLookup(),
      );
      await container
          .read(homeControllerProvider.notifier)
          .submit('show me my receipt');
      expect(container.read(homeControllerProvider).phase, HomePhase.error);
    });
  });

  group('inline surfaces render', () {
    testWidgets('a confirmation task renders the composed summary', (tester) async {
      final catalogue = _ScriptedCatalogue(
        intents: [
          _task(
            'confirmation',
            service: _service('svc_lagos', 'Lagos State Government', amount: 2500000),
            amount: 2500000,
          ),
        ],
      );
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: [
          catalogueRepositoryProvider.overrideWith((ref) => catalogue),
          receiptRepositoryProvider.overrideWith(
            (ref) => MockReceiptRepository(receipts: const []),
          ),
          surfaceRepositoryProvider.overrideWith(
            (ref) => MockSurfaceRepository(latency: Duration.zero),
          ),
        ],
      );
      await tester.pumpAndSettle();
      await _submit(tester, 'pay land use');
      expect(find.text('Lagos State Government'), findsOneWidget);
      expect(find.textContaining('25,000'), findsOneWidget);
      // The confirmation completes inline: the authorise action is the explicit
      // confirmation, and there is no route to a separate payment screen.
      expect(
        find.text(PaymentStrings.english.authorisePayment),
        findsOneWidget,
      );
    });

    testWidgets('a verification task renders the held surface', (tester) async {
      final catalogue = _ScriptedCatalogue(intents: [_task('verification')]);
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: [
          catalogueRepositoryProvider.overrideWith((ref) => catalogue),
          receiptRepositoryProvider.overrideWith(
            (ref) => MockReceiptRepository(receipts: const []),
          ),
          surfaceRepositoryProvider.overrideWith(
            (ref) => MockSurfaceRepository(latency: Duration.zero),
          ),
        ],
      );
      await tester.pumpAndSettle();
      await _submit(tester, 'pay a regulated bill');
      // The composed surface frames the task and keeps the Identity screen as
      // the alternate route...
      expect(
        find.text(SabStrings.english.openVerificationScreen),
        findsOneWidget,
      );
      expect(find.text(SabStrings.english.verifyInlineTitle), findsOneWidget);
      // ...and the ceremony completes inline: the shared task view collects the
      // NIN and offers the submit action in the conversation.
      expect(find.text('National Identity Number (NIN)'), findsOneWidget);
      expect(find.text('Verify identity'), findsWidgets);
    });

    testWidgets('a record lookup renders the receipt inline', (tester) async {
      final catalogue = _ScriptedCatalogue(
        intents: const [
          IntentResult(intentType: 'receipt_lookup', confidence: 0.9),
        ],
      );
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: [
          catalogueRepositoryProvider.overrideWith((ref) => catalogue),
          receiptRepositoryProvider.overrideWith(
            (ref) => MockReceiptRepository(receipts: const []),
          ),
          surfaceRepositoryProvider.overrideWith(
            (ref) => MockSurfaceRepository(latency: Duration.zero),
          ),
          recordLookupRepositoryProvider.overrideWith(
            (ref) => _ScriptedRecordLookup([
              ResolvedRecord(kind: 'receipt', id: 'rcp_1', receipt: _receipt()),
            ]),
          ),
        ],
      );
      await tester.pumpAndSettle();
      await _submit(tester, 'show me my December NEPA receipt');
      // The record's own fields are shown, and the existing screen stays
      // reachable as the alternate route.
      expect(find.text('Lagos State Government'), findsOneWidget);
      expect(find.text(SabStrings.english.openReceipt), findsOneWidget);
    });

    testWidgets('a no-record lookup renders the honest fallback, no card', (
      tester,
    ) async {
      final catalogue = _ScriptedCatalogue(
        intents: const [
          IntentResult(intentType: 'receipt_lookup', confidence: 0.9),
        ],
      );
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: [
          catalogueRepositoryProvider.overrideWith((ref) => catalogue),
          receiptRepositoryProvider.overrideWith(
            (ref) => MockReceiptRepository(receipts: const []),
          ),
          surfaceRepositoryProvider.overrideWith(
            (ref) => MockSurfaceRepository(latency: Duration.zero),
          ),
          recordLookupRepositoryProvider.overrideWith(
            (ref) => _ScriptedRecordLookup(const []),
          ),
        ],
      );
      await tester.pumpAndSettle();
      await _submit(tester, 'receipt for nothing');
      expect(find.text(SabStrings.english.noRecordTitle), findsOneWidget);
      // No fabricated receipt card is composed.
      expect(find.text('Lagos State Government'), findsNothing);
    });
  });
}

/// A record lookup that always fails, to assert a failure is never softened
/// into an invented record.
class _ThrowingRecordLookup implements RecordLookupRepository {
  @override
  Future<List<ResolvedRecord>> lookup(String query, {int limit = 5}) async =>
      throw const InvalidCredentialException();
}
