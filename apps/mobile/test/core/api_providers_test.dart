import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/api_config.dart';
import 'package:sabi_mobile/core/api_providers.dart';
import 'package:sabi_mobile/data/http_auth_repository.dart';
import 'package:sabi_mobile/data/http_repositories.dart';
import 'package:sabi_mobile/data/mock_repositories.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/features/payment/data/http_payment_repository.dart';
import 'package:sabi_mobile/features/payment/data/mock_payment_repository.dart';
import 'package:sabi_mobile/features/payment/data/providers.dart';

/// A container with the live flag pinned, without touching --dart-define.
ProviderContainer _container({required bool live}) {
  final container = ProviderContainer(
    overrides: [
      apiConfigProvider.overrideWithValue(
        ApiConfig(baseUrl: 'http://10.0.2.2:8000/v1', useLiveRepositories: live),
      ),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

void main() {
  test('the default build resolves the in-memory mocks', () {
    final container = _container(live: false);
    expect(container.read(authRepositoryProvider), isA<MockAuthRepository>());
    expect(
      container.read(catalogueRepositoryProvider),
      isA<MockCatalogueRepository>(),
    );
    expect(container.read(receiptRepositoryProvider), isA<MockReceiptRepository>());
    expect(container.read(receiptsRepositoryProvider), isA<MockReceiptsRepository>());
    expect(container.read(casesRepositoryProvider), isA<MockCasesRepository>());
    expect(container.read(paymentRepositoryProvider), isA<MockPaymentRepository>());
    expect(container.read(federalRepositoryProvider), isA<MockFederalRepository>());
    expect(container.read(billRepositoryProvider), isA<MockBillRepository>());
  });

  test('the live flag resolves every repository to its HTTP implementation', () {
    final container = _container(live: true);
    expect(container.read(authRepositoryProvider), isA<HttpAuthRepository>());
    expect(container.read(accountRepositoryProvider), isA<HttpAccountRepository>());
    expect(
      container.read(catalogueRepositoryProvider),
      isA<HttpCatalogueRepository>(),
    );
    expect(container.read(receiptRepositoryProvider), isA<HttpReceiptRepository>());
    expect(container.read(receiptsRepositoryProvider), isA<HttpReceiptsRepository>());
    expect(container.read(casesRepositoryProvider), isA<HttpCasesRepository>());
    expect(container.read(paymentRepositoryProvider), isA<HttpPaymentRepository>());
    expect(container.read(federalRepositoryProvider), isA<HttpFederalRepository>());
    expect(container.read(billRepositoryProvider), isA<HttpBillRepository>());
  });
}
