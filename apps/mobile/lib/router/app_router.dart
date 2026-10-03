import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../components/navigation_shell.dart';
import '../core/features.dart';
import '../data/providers.dart';
import '../features/account/account_screen.dart';
import '../features/account/verification/verification_screen.dart';
import '../features/case/case_screen.dart';
import '../features/home/home_screen.dart';
import '../features/payment/payment_confirmation_screen.dart';
import '../features/placeholder/gated_screen.dart';
import '../features/receipts/receipt_detail_screen.dart';
import '../features/receipts/receipts_screen.dart';
import '../features/sign_in/sign_in_screen.dart';
import '../features/welcome/welcome_screen.dart';

/// The navigation map from screens.md. Tabbed screens sit inside the shell;
/// task-first surfaces (Payment Confirmation, Identity Verification, Case) push
/// above it without the shell.
class SabRoutes {
  const SabRoutes._();

  static const welcome = '/welcome';
  static const signIn = '/sign-in';
  static const home = '/home';
  static const receipts = '/receipts';
  static const account = '/account';
  static const paymentConfirmation = '/pay';
  static const identityVerification = '/account/verify';

  static String payment(String serviceId) => '$paymentConfirmation/$serviceId';
  static String receipt(String receiptId) => '$receipts/$receiptId';
}

GoRouter buildRouter(Ref ref) {
  final session = ref.read(sessionProvider);
  final rootNavigatorKey = GlobalKey<NavigatorState>();
  const publicRoutes = {SabRoutes.welcome, SabRoutes.signIn};

  return GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: SabRoutes.welcome,
    refreshListenable: session,
    redirect: (context, state) {
      final location = state.matchedLocation;
      final isPublic = publicRoutes.contains(location);
      if (!session.isAuthenticated && !isPublic) {
        final from = Uri.encodeComponent(state.uri.toString());
        return '${SabRoutes.welcome}?from=$from';
      }
      if (session.isAuthenticated && isPublic) {
        return state.uri.queryParameters['from'] ?? SabRoutes.home;
      }
      return null;
    },
    routes: [
      GoRoute(
        path: SabRoutes.welcome,
        builder: (context, state) =>
            WelcomeScreen(from: state.uri.queryParameters['from']),
      ),
      GoRoute(
        path: SabRoutes.signIn,
        builder: (context, state) =>
            SignInScreen(from: state.uri.queryParameters['from']),
      ),
      // Task-first surfaces: no navigation shell.
      GoRoute(
        path: '${SabRoutes.paymentConfirmation}/:serviceId',
        builder: (context, state) => SabGatedScreen(
          feature: SabFeature.paymentAuthorization,
          title: state.pathParameters['serviceId'] ?? 'Payment',
          builder: (context) => PaymentConfirmationScreen(
            serviceId: state.pathParameters['serviceId'] ?? '',
          ),
        ),
      ),
      GoRoute(
        path: SabRoutes.identityVerification,
        builder: (context, state) => SabGatedScreen(
          feature: SabFeature.identityVerification,
          title: 'Identity',
          builder: (context) => VerificationScreen(
            fromPayment: state.uri.queryParameters['from'] == 'payment',
          ),
        ),
      ),
      GoRoute(
        path: '/cases/:caseId',
        builder: (context, state) => SabGatedScreen(
          feature: SabFeature.failureRecovery,
          title: 'Case',
          builder: (context) =>
              CaseScreen(caseId: state.pathParameters['caseId'] ?? ''),
        ),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            NavigationShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: SabRoutes.home,
                builder: (context, state) => const HomeScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: SabRoutes.receipts,
                builder: (context, state) => const ReceiptsScreen(),
                routes: [
                  GoRoute(
                    path: ':receiptId',
                    builder: (context, state) => SabGatedScreen(
                      feature: SabFeature.receiptCapture,
                      title: 'Receipt',
                      builder: (context) => ReceiptDetailScreen(
                        receiptId: state.pathParameters['receiptId'] ?? '',
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: SabRoutes.account,
                builder: (context, state) => const AccountScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      appBar: AppBar(title: const Text('Sabi')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            state.error?.toString() ?? 'Not found',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    ),
  );
}

final routerProvider = Provider<GoRouter>((ref) => buildRouter(ref));
