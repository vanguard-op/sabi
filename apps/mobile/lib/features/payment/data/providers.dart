import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/payment.dart';
import 'mock_payment_repository.dart';
import 'payment_repository.dart';

/// Payment repository wiring. Screens depend on the abstractions; the sandbox
/// implementations satisfy them until the endpoints are live, and this is the
/// one place to swap them (D-027).
final paymentRepositoryProvider = Provider<PaymentRepository>(
  (ref) => MockPaymentRepository(),
);

final federalRepositoryProvider = Provider<FederalRepository>(
  (ref) => MockFederalRepository(),
);

final billRepositoryProvider = Provider<BillRepository>(
  (ref) => MockBillRepository(),
);

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
