import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/composed_task_surface.dart';
import 'package:sabi_mobile/components/service_result_row.dart';
import 'package:sabi_mobile/components/skeleton.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/features/home/home_controller.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/intent_result.dart';
import 'package:sabi_mobile/models/receipt_summary.dart';
import 'package:sabi_mobile/models/service_summary.dart';

import '../helpers.dart';

/// A catalogue double whose intent resolution and search are controlled
/// independently, so the search fallback (FEAT-004) can be exercised even when
/// intent resolution finds nothing.
class _Catalogue implements CatalogueRepository {
  _Catalogue({this.intents = const [], this.searchResults = const []});

  final List<IntentResult> intents;
  final List<ServiceSummary> searchResults;
  int intentCalls = 0;
  int searchCalls = 0;

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
  }) async {
    final index = intentCalls < intents.length
        ? intentCalls
        : intents.length - 1;
    intentCalls++;
    return intents[index];
  }

  @override
  Future<CatalogueSearchResult> search(String query) async {
    searchCalls++;
    return CatalogueSearchResult(
      results: searchResults,
      noMatch: searchResults.isEmpty,
    );
  }

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async {
    // Home reads discovery only; the detail endpoint is not exercised here.
    throw const ServiceNotFoundException();
  }
}

IntentResult _lowConfidence(String question) => IntentResult(
  intentType: 'unknown',
  confidence: 0.3,
  clarifyingQuestion: question,
  candidates: const [
    ServiceSummary(
      serviceId: 'svc_electric',
      name: 'Electricity token',
      collectingBody: 'Ikeja Electric',
      category: 'Biller',
      confidence: 0.45,
    ),
  ],
);

ServiceSummary _service(String id, String body) => ServiceSummary(
  serviceId: id,
  name: 'Land Use Charge',
  collectingBody: body,
  category: 'Government',
  confidence: 0.8,
);

/// The composer's send action. `tooltip` creates a [Tooltip] above the
/// [IconButton], so the button is found through its tooltip's ancestor.
final Finder _sendButton = find.ancestor(
  of: find.byTooltip('Send'),
  matching: find.byType(IconButton),
);

ReceiptSummary _receipt(String id, String payee, PaymentStatus status) =>
    ReceiptSummary(
      id: id,
      reference: 'REF-$id',
      payee: payee,
      amount: 150000,
      currency: 'NGN',
      kind: 'Biller',
      status: status,
      issuedAt: DateTime.utc(2026, 9, 20),
    );

List<Override> _overrides({
  Duration latency = Duration.zero,
  List<ReceiptSummary>? receipts,
  CatalogueRepository? catalogue,
}) => [
  receiptRepositoryProvider.overrideWith(
    (ref) => MockReceiptRepository(latency: latency, receipts: receipts),
  ),
  catalogueRepositoryProvider.overrideWith(
    (ref) => catalogue ?? MockCatalogueRepository(latency: Duration.zero),
  ),
];

void main() {
  testWidgets('first load shows the skeleton', (tester) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(
        latency: const Duration(milliseconds: 200),
        receipts: [_receipt('1', 'MTN Nigeria', PaymentStatus.settled)],
      ),
    );
    await tester.pump();
    expect(find.byType(SabSkeletonList), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.byType(SabSkeletonList), findsNothing);
  });

  testWidgets('no history shows the empty state', (tester) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    expect(find.text('No payments yet'), findsOneWidget);
  });

  testWidgets('loaded shows recent receipts with their status', (tester) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(
        receipts: [
          _receipt('1', 'Lagos State Government', PaymentStatus.settled),
          _receipt('2', 'MTN Nigeria', PaymentStatus.pending),
        ],
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Lagos State Government'), findsOneWidget);
    expect(find.text('MTN Nigeria'), findsOneWidget);
    expect(find.text('Settled'), findsOneWidget);
    expect(find.text('Pending'), findsOneWidget);
  });

  testWidgets('a request in flight disables the composer', (tester) async {
    final controller = MockCatalogueRepository(
      latency: const Duration(milliseconds: 200),
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const [], catalogue: controller),
    );
    await tester.pumpAndSettle();
    final future = containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('pay my land use charge');
    await tester.pump();
    expect(find.text('Working on it…'), findsOneWidget);
    final textField = tester.widget<TextField>(find.byType(TextField));
    expect(textField.enabled, isFalse);
    // Advance the fake clock so the pending resolution completes.
    await tester.pumpAndSettle();
    await future;
  });

  testWidgets('discovery results render as selectable service rows', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('pay my land use charge');
    await tester.pumpAndSettle();
    expect(find.text('Lagos State Government'), findsOneWidget);
    expect(find.text('Land Use Charge'), findsOneWidget);
  });

  testWidgets('low confidence asks one question with the closest candidates', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('I wan pay my electricity');
    await tester.pumpAndSettle();
    expect(find.text('Just to confirm'), findsOneWidget);
    expect(find.text('Which electricity provider do you pay?'), findsOneWidget);
    expect(find.text('Ikeja Electric'), findsOneWidget);
  });

  testWidgets(
    'a catalogue miss states the gap instead of inventing a service',
    (tester) async {
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(receipts: const []),
      );
      await tester.pumpAndSettle();
      containerOf(tester)
          .read(homeControllerProvider.notifier)
          .submit('pay my xyz subscription');
      await tester.pumpAndSettle();
      expect(find.text('Not covered yet'), findsOneWidget);
      expect(find.text('Contact support'), findsOneWidget);
    },
  );

  testWidgets(
    'a resolution failure offers a retry that preserves the request',
    (tester) async {
      final controller = MockCatalogueRepository(latency: Duration.zero)
        ..failNext = true;
      await pumpSab(
        tester,
        const HomeScreen(),
        overrides: _overrides(receipts: const [], catalogue: controller),
      );
      await tester.pumpAndSettle();
      containerOf(tester)
          .read(homeControllerProvider.notifier)
          .submit('pay my land use charge');
      await tester.pumpAndSettle();
      expect(
        find.text(
          'We couldn’t work that out. Check your connection and try again.',
        ),
        findsOneWidget,
      );
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      // The retry resolves the preserved request.
      expect(find.text('Lagos State Government'), findsOneWidget);
    },
  );

  testWidgets('offline queues the request and blocks authorisation', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    containerOf(tester).read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();
    expect(
      find.text('Payments can’t be authorised while you’re offline.'),
      findsOneWidget,
    );
    containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('pay my land use charge');
    await tester.pumpAndSettle();
    expect(
      find.text(
        'Your request is queued and will send when you’re back online.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('a resolved request shows the user words above the result', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'pay my land use charge');
    await tester.pump();
    await tester.tap(_sendButton);
    await tester.pumpAndSettle();
    expect(find.text('pay my land use charge'), findsOneWidget);
    expect(find.text('Lagos State Government'), findsOneWidget);
  });

  testWidgets('a single match stays a selectable discovery result', (
    tester,
  ) async {
    final catalogue = _Catalogue(
      intents: [
        IntentResult(
          intentType: 'bill_payment',
          confidence: 0.95,
          candidates: [_service('svc_mtn', 'MTN Nigeria')],
        ),
      ],
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const [], catalogue: catalogue),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'buy airtime');
    await tester.pump();
    await tester.tap(_sendButton);
    await tester.pumpAndSettle();
    // Not auto-navigated: the composed discovery surface is shown and the row
    // is selectable (FEAT-004).
    expect(find.byType(ComposedTaskSurface), findsOneWidget);
    expect(find.byType(ServiceResultRow), findsOneWidget);
    expect(find.text('MTN Nigeria'), findsOneWidget);
  });

  testWidgets('a catalogue search reaches discovery when intent finds none', (
    tester,
  ) async {
    final catalogue = _Catalogue(
      intents: const [IntentResult(intentType: 'unknown', confidence: 0.2)],
      searchResults: [_service('svc_onitsha', 'Onitsha North LGA')],
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const [], catalogue: catalogue),
    );
    await tester.pumpAndSettle();
    containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('council levy Onitsha');
    await tester.pumpAndSettle();
    expect(catalogue.searchCalls, 1);
    expect(find.text('Onitsha North LGA'), findsOneWidget);
  });

  testWidgets('a second unresolved answer narrows into a second question', (
    tester,
  ) async {
    final catalogue = _Catalogue(
      intents: [
        _lowConfidence('Which electricity provider do you pay?'),
        _lowConfidence('Which one do you mean?'),
      ],
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const [], catalogue: catalogue),
    );
    await tester.pumpAndSettle();
    final controller = containerOf(tester)
        .read(homeControllerProvider.notifier);
    await controller.submit('I wan pay my electricity');
    await tester.pumpAndSettle();
    expect(find.text('Just to confirm'), findsOneWidget);
    // The conversation may ask up to three questions, so a second unresolved
    // answer is narrowed into a second question rather than abandoned to the
    // not-covered state (FEAT-003).
    await controller.submit('Ikeja');
    await tester.pumpAndSettle();
    expect(find.text('Which one do you mean?'), findsOneWidget);
    expect(find.text('Not covered yet'), findsNothing);
    // Both requests remain in the conversation, oldest first.
    expect(find.text('I wan pay my electricity'), findsOneWidget);
    expect(find.text('Ikeja'), findsOneWidget);
  });

  testWidgets('a coverage miss offers human support', (tester) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('pay my xyz subscription');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Contact support'));
    await tester.pumpAndSettle();
    // The support dialog carries the not-covered explanation and a close action.
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.text('Close'), findsOneWidget);
  });

  testWidgets('an awaiting-receipt payment shows its status on Home', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(
        receipts: [
          _receipt('1', 'Ikeja Electric', PaymentStatus.awaitingReceipt),
        ],
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Awaiting receipt'), findsOneWidget);
  });

  testWidgets('the composer sends only when there is text', (tester) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    final send = tester.widget<IconButton>(_sendButton);
    expect(send.onPressed, isNull);
    await tester.enterText(find.byType(TextField), 'pay light');
    await tester.pump();
    final sendReady = tester.widget<IconButton>(_sendButton);
    expect(sendReady.onPressed, isNotNull);
  });

  testWidgets('a long request wraps and keeps the send action reachable', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'x' * 200);
    await tester.pump();
    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.maxLength, homeRequestMaxLength);
    expect(field.maxLines, greaterThan(1));
    expect(_sendButton, findsOneWidget);
    expect(tester.widget<IconButton>(_sendButton).onPressed, isNotNull);
  });

  testWidgets('a new request appends and keeps the earlier result visible', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    final controller = containerOf(tester)
        .read(homeControllerProvider.notifier);
    controller.submit('pay my land use charge');
    await tester.pumpAndSettle();
    // A second, unrelated request must not clear the first exchange.
    controller.submit('buy airtime');
    await tester.pumpAndSettle();
    expect(find.text('pay my land use charge'), findsOneWidget);
    expect(find.text('buy airtime'), findsOneWidget);
    expect(find.text('Lagos State Government'), findsOneWidget);
    expect(find.text('MTN Nigeria'), findsOneWidget);
    // Both requests are preserved as turns, oldest first.
    expect(
      containerOf(tester).read(homeControllerProvider).turns,
      hasLength(2),
    );
  });

  testWidgets('a provider-picker round trip preserves the turns', (
    tester,
  ) async {
    final catalogue = _Catalogue(
      intents: [
        IntentResult(
          intentType: 'bill_payment',
          confidence: 0.9,
          candidates: [
            _service('svc_onitsha_north', 'Onitsha North LGA'),
            _service('svc_onitsha_south', 'Onitsha South LGA'),
          ],
        ),
      ],
    );
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const [], catalogue: catalogue),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'council levy');
    await tester.pump();
    await tester.tap(_sendButton);
    await tester.pumpAndSettle();
    // The sheet blocks on a choice; the conversation stays behind it.
    expect(find.text('Which one do you mean?'), findsOneWidget);
    // Dismiss without choosing: the turns are still there afterwards.
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    expect(find.text('Which one do you mean?'), findsNothing);
    expect(find.text('council levy'), findsOneWidget);
    expect(find.text('Onitsha North LGA'), findsOneWidget);
  });

  testWidgets('an offline queued request stays in the conversation', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const []),
    );
    await tester.pumpAndSettle();
    final container = containerOf(tester);
    container.read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();
    await container
        .read(homeControllerProvider.notifier)
        .submit('pay my land use charge');
    await tester.pumpAndSettle();
    // The request is preserved as a turn and the banner explains it is queued.
    expect(find.text('pay my land use charge'), findsOneWidget);
    expect(
      find.text(
        'Your request is queued and will send when you’re back online.',
      ),
      findsOneWidget,
    );
    // A later, second queued request appends without discarding the first.
    await container.read(homeControllerProvider.notifier).submit('buy airtime');
    await tester.pumpAndSettle();
    expect(find.text('pay my land use charge'), findsOneWidget);
    expect(find.text('buy airtime'), findsOneWidget);
  });

  testWidgets('a retry re-runs the request in place without duplicating it', (
    tester,
  ) async {
    final catalogue = MockCatalogueRepository(latency: Duration.zero)
      ..failNext = true;
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(receipts: const [], catalogue: catalogue),
    );
    await tester.pumpAndSettle();
    containerOf(tester)
        .read(homeControllerProvider.notifier)
        .submit('pay my land use charge');
    await tester.pumpAndSettle();
    expect(find.text('pay my land use charge'), findsOneWidget);
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('Lagos State Government'), findsOneWidget);
    // The request bubble is not duplicated by the retry.
    expect(find.text('pay my land use charge'), findsOneWidget);
    expect(
      containerOf(tester).read(homeControllerProvider).turns,
      hasLength(1),
    );
  });
}
