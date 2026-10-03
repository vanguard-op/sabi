import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_providers.dart';
import '../../../data/providers.dart';
import '../../../data/repositories.dart';
import '../../../models/service_summary.dart';
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
/// service id.
///
/// The mock/offline build resolves from the sandbox catalogue so the demo build
/// and the widget tests never open a socket. The live build fetches the service
/// from the catalogue (C-011) and derives the flow kind from its `type`:
/// `government` is the federal collection flow (FEAT-006), `biller` the
/// everyday bill flow (FEAT-007), and `merchant` the shared authorise-and-
/// execute path (FEAT-005). Kept as a provider so a test can open any branch by
/// overriding it, and so the live version resolves from the catalogue rather
/// than a hardcoded sandbox entry.
final paymentObligationProvider =
    FutureProvider.family<PaymentObligation, String>((ref, serviceId) async {
      if (!ref.watch(apiConfigProvider).useLiveRepositories) {
        return PaymentObligation.fromService(
          PaymentSandboxCatalogue.serviceFor(serviceId),
          kind: PaymentSandboxCatalogue.kindFor(serviceId),
        );
      }
      final service = await ref
          .watch(catalogueRepositoryProvider)
          .serviceDetail(serviceId);
      return PaymentObligation.fromService(
        _toSummary(service),
        kind: _kindForServiceType(service.type),
      );
    });

PaymentKind _kindForServiceType(String type) => switch (type) {
  'government' => PaymentKind.federal,
  'biller' => PaymentKind.bill,
  _ => PaymentKind.standard,
};

ServiceSummary _toSummary(CatalogueService service) => ServiceSummary(
  serviceId: service.id,
  name: service.name,
  collectingBody: service.collectingBody,
  category: service.category,
  knownAmount: service.knownAmount,
  currency: service.currency,
  status: service.status,
);
