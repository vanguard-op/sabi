import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/api_exception.dart';
import 'package:sabi_mobile/core/api_providers.dart';
import 'package:sabi_mobile/core/session.dart';
import 'package:sabi_mobile/data/providers.dart';
import 'package:sabi_mobile/data/repositories.dart';
import 'package:sabi_mobile/l10n/sab_strings.dart';
import 'package:sabi_mobile/models/account.dart';
import 'package:sabi_mobile/models/channel_link.dart';
import 'package:sabi_mobile/models/payment_method.dart';

class _MemoryStorage implements SessionCookieStorage {
  _MemoryStorage([this.value]);

  String? value;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String value) async => this.value = value;

  @override
  Future<void> clear() async => value = null;
}

class _FakeAccountRepository implements AccountRepository {
  _FakeAccountRepository({this.account, this.error});

  final Account? account;
  final Object? error;
  int calls = 0;

  @override
  Future<Account> me() async {
    calls++;
    if (error != null) throw error!;
    return account!;
  }

  @override
  Future<Account> updateLocale(AppLocale locale) => me();

  @override
  Future<ChannelLink> linkChannel({
    required String channel,
    required String address,
  }) async => throw UnimplementedError();

  @override
  Future<List<PaymentMethod>> paymentMethods() async => const [];
}

Account _account() => const Account(
  id: 'usr_1',
  locale: 'en',
  preferredChannel: 'app',
  kycStatus: VerificationStatus.unverified,
  accountStatus: 'active',
);

({
  ProviderContainer container,
  SessionStore session,
  _FakeAccountRepository repository,
  _MemoryStorage storage,
})
_build({
  String? cookie,
  Account? account,
  Object? error,
  SessionStore? preset,
}) {
  final storage = _MemoryStorage(cookie);
  final repository = _FakeAccountRepository(account: account, error: error);
  final container = ProviderContainer(
    overrides: [
      sessionCookieStoreProvider.overrideWithValue(
        SessionCookieStore(storage: storage),
      ),
      accountRepositoryProvider.overrideWith((ref) => repository),
      if (preset != null) sessionProvider.overrideWithValue(preset),
    ],
  );
  addTearDown(container.dispose);
  return (
    container: container,
    session: container.read(sessionProvider),
    repository: repository,
    storage: storage,
  );
}

void main() {
  test('no persisted cookie resolves straight to signed out', () async {
    final ctx = _build();

    await ctx.container.read(sessionBootstrapProvider.future);

    expect(ctx.session.status, SessionStatus.unauthenticated);
    expect(ctx.repository.calls, 0);
  });

  test('a verified cookie resolves the session authenticated', () async {
    final ctx = _build(cookie: 'good.token', account: _account());

    await ctx.container.read(sessionBootstrapProvider.future);

    expect(ctx.session.status, SessionStatus.authenticated);
    expect(ctx.repository.calls, 1);
    expect(ctx.storage.value, 'good.token');
  });

  test(
    'a rejected cookie is cleared and the session stays signed out',
    () async {
      final ctx = _build(
        cookie: 'dead.token',
        error: const ApiUnauthenticated(),
      );

      await ctx.container.read(sessionBootstrapProvider.future);

      expect(ctx.session.status, SessionStatus.unauthenticated);
      expect(ctx.storage.value, isNull);
    },
  );

  test('an offline launch stays signed out but keeps the cookie', () async {
    final ctx = _build(cookie: 'kept.token', error: const ApiUnreachable());

    await ctx.container.read(sessionBootstrapProvider.future);

    expect(ctx.session.status, SessionStatus.unauthenticated);
    expect(ctx.storage.value, 'kept.token');
  });

  test('an already-resolved session is left untouched', () async {
    final preset = SessionStore()..signIn();
    final ctx = _build(preset: preset);

    await ctx.container.read(sessionBootstrapProvider.future);

    expect(ctx.session, same(preset));
    expect(ctx.session.status, SessionStatus.authenticated);
    expect(ctx.repository.calls, 0);
  });
}
