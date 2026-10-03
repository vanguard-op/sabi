import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/components/skeleton.dart';
import 'package:sabi_mobile/core/connectivity.dart';
import 'package:sabi_mobile/design_system/sab_art.dart';
import 'package:sabi_mobile/design_system/theme.dart';
import 'package:sabi_mobile/features/account/verification/verification_controller.dart';
import 'package:sabi_mobile/features/account/verification/verification_mock.dart';
import 'package:sabi_mobile/features/account/verification/verification_models.dart';
import 'package:sabi_mobile/features/account/verification/verification_screen.dart';

/// Pumps the verification screen directly, without the app router, so this
/// feature's tests stay independent of the in-flight sibling feature work.
/// Static art only: no Rive decode runs in a unit test.
Future<void> _pump(
  WidgetTester tester, {
  MockVerificationRepository? repo,
  bool fromPayment = false,
  Brightness brightness = Brightness.light,
}) async {
  await tester.pumpWidget(
    SabArtMode(
      staticOnly: true,
      child: ProviderScope(
        overrides: [
          verificationRepositoryProvider.overrideWith(
            (ref) => repo ?? MockVerificationRepository(latency: Duration.zero),
          ),
        ],
        child: MaterialApp(
          theme: buildSabTheme(brightness),
          home: VerificationScreen(fromPayment: fromPayment),
        ),
      ),
    ),
  );
}

ProviderContainer _container(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(MaterialApp)));

/// A repository whose status call always fails, for the load-error state.
class _FailingStatusRepository extends MockVerificationRepository {
  _FailingStatusRepository() : super(latency: Duration.zero);

  @override
  Future<AccountVerification> status() async =>
      throw Exception('transport down');
}

void main() {
  testWidgets('loading shows a skeleton before the status resolves', (
    tester,
  ) async {
    await _pump(
      tester,
      repo: MockVerificationRepository(
        latency: const Duration(milliseconds: 200),
      ),
    );
    await tester.pump();
    expect(find.byType(SabSkeletonList), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.byType(SabSkeletonList), findsNothing);
  });

  testWidgets('default shows the unverified pill, field, and the action', (
    tester,
  ) async {
    await _pump(tester);
    await tester.pumpAndSettle();
    expect(find.text('Not verified'), findsOneWidget);
    expect(find.text('National Identity Number (NIN)'), findsOneWidget);
    // BVN only appears when the rail requires it; the default mock does not.
    expect(find.text('Bank Verification Number (BVN)'), findsNothing);
    expect(find.text('Verify identity'), findsWidgets);
    expect(find.textContaining('national identity provider'), findsOneWidget);
  });

  testWidgets('an empty identifier is refused with a validation message', (
    tester,
  ) async {
    await _pump(tester);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Verify identity'));
    await tester.pumpAndSettle();
    expect(find.text('Enter this number to continue.'), findsOneWidget);
  });

  testWidgets('a rejected identifier is refused with a field error', (
    tester,
  ) async {
    await _pump(tester);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, '123');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Verify identity'));
    await tester.pumpAndSettle();
    expect(
      find.text('A NIN is 11 digits. Check the number and try again.'),
      findsOneWidget,
    );
  });

  testWidgets('checking locks the fields and shows progress on the action', (
    tester,
  ) async {
    final repo = MockVerificationRepository(
      latency: const Duration(milliseconds: 300),
    );
    await _pump(tester, repo: repo);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, '12345678901');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Verify identity'));
    await tester.pump();
    expect(find.text('Checking your details…'), findsOneWidget);
    final field = tester.widget<TextField>(find.byType(TextField).first);
    expect(field.enabled, isFalse);
    await tester.pumpAndSettle();
    // The mock verifies a well-formed identifier, so the state settles done.
    expect(find.text('You are verified'), findsOneWidget);
  });

  testWidgets('verified shows the verified status and no further action', (
    tester,
  ) async {
    await _pump(
      tester,
      repo: MockVerificationRepository(
        latency: Duration.zero,
        initialStatus: KycStatus.verified,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Verified'), findsOneWidget);
    expect(find.text('You are verified'), findsOneWidget);
    expect(find.text('Back to account'), findsOneWidget);
    expect(find.text('Verify identity'), findsNothing);
  });

  testWidgets('a verified held payment offers the payment resume action', (
    tester,
  ) async {
    await _pump(
      tester,
      fromPayment: true,
      repo: MockVerificationRepository(
        latency: Duration.zero,
        initialStatus: KycStatus.verified,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Back to payment'), findsOneWidget);
    expect(find.text('Back to account'), findsNothing);
  });

  testWidgets('a held payment is announced while unverified', (tester) async {
    await _pump(tester, fromPayment: true);
    await tester.pumpAndSettle();
    expect(find.text('This payment is held'), findsOneWidget);
    expect(
      find.textContaining('will resume once you are verified'),
      findsOneWidget,
    );
  });

  testWidgets('no match states a reason and allows one correction', (
    tester,
  ) async {
    final repo = MockVerificationRepository(latency: Duration.zero)
      ..failNextMatch = true;
    await _pump(tester, repo: repo);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, '12345678901');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Verify identity'));
    await tester.pumpAndSettle();
    expect(find.text('No match found'), findsOneWidget);
    expect(find.text('Correct my details'), findsOneWidget);
    expect(find.text('Verify identity'), findsNothing);
  });

  testWidgets('a second failed correction routes to support', (tester) async {
    final repo = MockVerificationRepository(latency: Duration.zero)
      ..failNextMatch = true;
    await _pump(tester, repo: repo);
    await tester.pumpAndSettle();

    // First failure offers the single correction.
    await tester.enterText(find.byType(TextField).first, '12345678901');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Verify identity'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Correct my details'));
    await tester.pumpAndSettle();

    // The correction fails too; the form is gone and support is offered.
    repo.failNextMatch = true;
    await tester.enterText(find.byType(TextField).first, '12345678901');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Verify identity'));
    await tester.pumpAndSettle();
    expect(find.text('Contact support'), findsOneWidget);
    expect(find.text('Correct my details'), findsNothing);
    expect(find.text('Verify identity'), findsNothing);
  });

  testWidgets('an unavailable provider reports the check as pending', (
    tester,
  ) async {
    final repo = MockVerificationRepository(latency: Duration.zero)
      ..providerAvailable = false;
    await _pump(tester, repo: repo);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, '12345678901');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Verify identity'));
    await tester.pumpAndSettle();
    expect(find.text('Pending'), findsOneWidget);
    expect(find.text('Verification pending'), findsOneWidget);
    expect(find.textContaining('keep using discovery'), findsOneWidget);
  });

  testWidgets('a rejected account states the reason and routes to support', (
    tester,
  ) async {
    await _pump(
      tester,
      repo: MockVerificationRepository(
        latency: Duration.zero,
        initialStatus: KycStatus.rejected,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Rejected'), findsOneWidget);
    expect(find.text('Verification rejected'), findsOneWidget);
    expect(find.text('Contact support'), findsOneWidget);
    expect(find.text('Verify identity'), findsNothing);
  });

  testWidgets('a load failure offers a retry', (tester) async {
    await _pump(tester, repo: _FailingStatusRepository());
    await tester.pumpAndSettle();
    expect(
      find.text('We couldn’t load your verification status.'),
      findsOneWidget,
    );
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('offline disables submission and shows the banner', (
    tester,
  ) async {
    await _pump(tester);
    await tester.pumpAndSettle();
    _container(tester).read(connectivityProvider.notifier).setOnline(false);
    await tester.pumpAndSettle();
    expect(
      find.text('You’re offline. Verification needs a connection to run.'),
      findsOneWidget,
    );
    final state = _container(tester).read(verificationControllerProvider);
    expect(state.online, isFalse);
    expect(state.canSubmit, isFalse);
  });

  testWidgets('renders on the dark token set', (tester) async {
    await _pump(tester, brightness: Brightness.dark);
    await tester.pumpAndSettle();
    expect(find.text('Not verified'), findsOneWidget);
  });
}
