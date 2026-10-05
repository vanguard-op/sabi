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
import 'package:sabi_mobile/features/account/verification/verification_controller.dart';
import 'package:sabi_mobile/features/account/verification/verification_mock.dart';
import 'package:sabi_mobile/features/account/verification/verification_models.dart';
import 'package:sabi_mobile/features/account/verification/verification_strings.dart';
import 'package:sabi_mobile/features/account/verification/verification_task_view.dart';
import 'package:sabi_mobile/features/home/home_controller.dart';
import 'package:sabi_mobile/features/home/home_screen.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/intent_result.dart';

import '../../helpers.dart';

/// A catalogue whose settled intent is the identity task, so the inline
/// ceremony is reached deterministically.
class _VerificationCatalogue implements CatalogueRepository {
  _VerificationCatalogue({this.reply});

  final String? reply;

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  }) async => IntentResult(
    intentType: 'verification',
    reply: reply,
    confidence: 0.9,
    constraints: const {'task': 'verification'},
  );

  @override
  Future<CatalogueSearchResult> search(String query) async =>
      const CatalogueSearchResult(results: [], noMatch: true);

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async =>
      throw const ServiceNotFoundException();
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

List<Override> _overrides({
  String? reply,
  MockVerificationRepository? verification,
  SurfaceRepository? surface,
}) => [
  catalogueRepositoryProvider.overrideWith(
    (ref) => _VerificationCatalogue(reply: reply),
  ),
  receiptRepositoryProvider.overrideWith(
    (ref) => MockReceiptRepository(receipts: const []),
  ),
  surfaceRepositoryProvider.overrideWith(
    (ref) => surface ?? MockSurfaceRepository(latency: Duration.zero),
  ),
  verificationRepositoryProvider.overrideWith(
    (ref) => verification ?? MockVerificationRepository(latency: Duration.zero),
  ),
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

/// The inline NIN field, distinguished from the Home composer.
Finder _ninField() => find
    .descendant(
      of: find.byType(VerificationTaskView),
      matching: find.byType(TextField),
    )
    .first;

Finder _verifyButton() => find.descendant(
  of: find.byType(VerificationTaskView),
  matching: find.widgetWithText(
    ElevatedButton,
    VerificationStrings.english.verify,
  ),
);

void main() {
  testWidgets('the identity ceremony renders inline in the conversation', (
    tester,
  ) async {
    await pumpSab(tester, const HomeScreen(), overrides: _overrides());
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    // The task is the inline ceremony, not a route: the composed surface frames
    // it and the shared shell collects the details in the conversation.
    expect(
      containerOf(tester).read(homeControllerProvider).phase,
      HomePhase.verifying,
    );
    expect(find.byType(VerificationTaskView), findsOneWidget);
    expect(find.text('National Identity Number (NIN)'), findsOneWidget);
    expect(_verifyButton(), findsOneWidget);
  });

  testWidgets('the agent-composed surface frames the task above the form', (
    tester,
  ) async {
    const reply = 'Verify your identity to release the payment.';
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(reply: reply),
    );
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    // The composed surface carries the agent's own copy above the client shell.
    expect(find.text(reply), findsOneWidget);
    expect(find.byType(VerificationTaskView), findsOneWidget);
  });

  testWidgets('a valid identifier completes the ceremony inline', (
    tester,
  ) async {
    await pumpSab(tester, const HomeScreen(), overrides: _overrides());
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    await tester.enterText(_ninField(), '12345678901');
    await tester.tap(_verifyButton());
    await tester.pumpAndSettle();

    // C-020/C-021/C-022 ran through the controller and the result shows in the
    // conversation: verified, with no route taken.
    expect(
      containerOf(tester).read(verificationControllerProvider).phase,
      VerificationPhase.verified,
    );
    expect(
      find.text(VerificationStrings.english.verifiedTitle),
      findsOneWidget,
    );
    expect(
      find.text(VerificationStrings.english.statusVerified),
      findsOneWidget,
    );
    expect(_verifyButton(), findsNothing);
  });

  testWidgets('an empty identifier is refused inline with a field error', (
    tester,
  ) async {
    await pumpSab(tester, const HomeScreen(), overrides: _overrides());
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    await tester.tap(_verifyButton());
    await tester.pumpAndSettle();
    expect(
      find.text(VerificationStrings.english.requiredField),
      findsOneWidget,
    );
  });

  testWidgets('a rejected identifier is refused inline with a field error', (
    tester,
  ) async {
    await pumpSab(tester, const HomeScreen(), overrides: _overrides());
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    await tester.enterText(_ninField(), '123');
    await tester.tap(_verifyButton());
    await tester.pumpAndSettle();
    expect(find.text(VerificationStrings.english.invalidNin), findsOneWidget);
  });

  testWidgets('no match offers one correction inline, then support', (
    tester,
  ) async {
    final repo = MockVerificationRepository(latency: Duration.zero)
      ..failNextMatch = true;
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(verification: repo),
    );
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    // First failure: a plain reason and the single correction, in the
    // conversation.
    await tester.enterText(_ninField(), '12345678901');
    await tester.tap(_verifyButton());
    await tester.pumpAndSettle();
    expect(find.text(VerificationStrings.english.noMatchTitle), findsOneWidget);
    expect(
      find.text(VerificationStrings.english.correctDetails),
      findsOneWidget,
    );

    // The correction fails too: the form is gone and support is offered rather
    // than looping a second correction.
    await tester.tap(find.text(VerificationStrings.english.correctDetails));
    await tester.pumpAndSettle();
    repo.failNextMatch = true;
    await tester.enterText(_ninField(), '12345678901');
    await tester.tap(_verifyButton());
    await tester.pumpAndSettle();
    expect(
      find.text(VerificationStrings.english.contactSupport),
      findsOneWidget,
    );
    expect(
      find.text(VerificationStrings.english.correctDetails),
      findsNothing,
    );
  });

  testWidgets('an unavailable provider reports the check pending inline', (
    tester,
  ) async {
    final repo = MockVerificationRepository(latency: Duration.zero)
      ..providerAvailable = false;
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(verification: repo),
    );
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    await tester.enterText(_ninField(), '12345678901');
    await tester.tap(_verifyButton());
    await tester.pumpAndSettle();
    expect(find.text(VerificationStrings.english.pendingTitle), findsOneWidget);
    expect(
      find.textContaining('keep using discovery'),
      findsOneWidget,
    );
  });

  testWidgets('an already-verified account shows the status, not the form', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(
        verification: MockVerificationRepository(
          latency: Duration.zero,
          initialStatus: KycStatus.verified,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    // No repeat verification is requested (FEAT-002, alternate C).
    expect(
      find.text(VerificationStrings.english.verifiedTitle),
      findsOneWidget,
    );
    expect(_verifyButton(), findsNothing);
  });

  testWidgets('a failed composition still renders the prewritten form', (
    tester,
  ) async {
    await pumpSab(
      tester,
      const HomeScreen(),
      overrides: _overrides(surface: _NoCompositionSurface()),
    );
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    // The task stays completable: the client's own form carries it when the
    // agent composes nothing.
    expect(
      containerOf(tester).read(homeControllerProvider).surfaceTask,
      SurfaceTask.verification,
    );
    expect(find.byType(VerificationTaskView), findsOneWidget);
    expect(find.text('National Identity Number (NIN)'), findsOneWidget);
    expect(_verifyButton(), findsOneWidget);
  });

  testWidgets('offline replaces the submit action with the offline note', (
    tester,
  ) async {
    await pumpSab(tester, const HomeScreen(), overrides: _overrides());
    await tester.pumpAndSettle();
    await _submitRequest(tester, 'verify me');

    containerOf(tester).read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();

    expect(
      find.text(VerificationStrings.english.offlineAction),
      findsOneWidget,
    );
    expect(_verifyButton(), findsNothing);
    expect(
      containerOf(tester).read(verificationControllerProvider).canSubmit,
      isFalse,
    );
  });
}
