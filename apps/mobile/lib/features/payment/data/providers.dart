import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_providers.dart';
import '../models/payment.dart';
import 'http_payment_repository.dart';
import 'mock_payment_repository.dart';
import 'payment_repository.dart';

/// Payment repository wiring. Screens depend on the abstractions; the sandbox
/// satisfies them by default, and the `USE_LIVE_REPOSITORIES` build flag swaps
/// in the HTTP implementations against the gateway (D-027).
final paymentRepositoryProvider = Provider<PaymentRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpPaymentRepository(ref.watch(apiClientProvider));
  }
  return MockPaymentRepository();
});

final federalRepositoryProvider = Provider<FederalRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpFederalRepository(ref.watch(apiClientProvider));
  }
  return MockFederalRepository();
});

final billRepositoryProvider = Provider<BillRepository>((ref) {
  if (ref.watch(apiConfigProvider).useLiveRepositories) {
    return HttpBillRepository(ref.watch(apiClientProvider));
  }
  return MockBillRepository();
});

/// The obligation the confirmation surface renders, resolved from the route's
/// service id. The kind selects the flow: a federal collection resolves and
/// reconciles, a bill validates a recipient, and a standard obligation shares
/// the common authorise-and-execute path.
///
/// Kept as a provider so a test can open any branch by overriding it, and so
/// the live version can resolve from the catalogue instead of the sandbox.
final paymentObligationProvider = Provider.family<PaymentObligation, String>((
  ref,
  serviceId,
) {
  final kind = PaymentSandboxCatalogue.kindFor(serviceId);
  return PaymentObligation.fromService(
    PaymentSandboxCatalogue.serviceFor(serviceId),
    kind: kind,
  );
});
