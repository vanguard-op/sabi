import 'package:flutter_test/flutter_test.dart';
import 'package:sabi_mobile/core/session.dart';

/// An in-memory stand-in for the platform keystore.
class _MemoryStorage implements SessionCookieStorage {
  String? value;
  int writes = 0;
  int clears = 0;
  bool failRead = false;

  @override
  Future<String?> read() async {
    if (failRead) throw StateError('keystore unavailable');
    return value;
  }

  @override
  Future<void> write(String value) async {
    writes++;
    this.value = value;
  }

  @override
  Future<void> clear() async {
    clears++;
    value = null;
  }
}

const _sessionCookie =
    'sabi_session=tok.abc.123; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax; Secure';

void main() {
  group('capture', () {
    test('a session Set-Cookie is held and persisted', () async {
      final storage = _MemoryStorage();
      final store = SessionCookieStore(storage: storage);

      await store.capture([_sessionCookie]);

      expect(store.hasSession, isTrue);
      expect(store.cookieHeader, 'sabi_session=tok.abc.123');
      expect(storage.value, 'tok.abc.123');
    });

    test('a non-session cookie is ignored', () async {
      final store = SessionCookieStore(storage: _MemoryStorage());

      await store.capture(['theme=dark; Path=/; HttpOnly']);

      expect(store.hasSession, isFalse);
      expect(store.cookieHeader, isNull);
    });

    test(
      'the session cookie is found among several Set-Cookie values',
      () async {
        final store = SessionCookieStore(storage: _MemoryStorage());

        await store.capture(['theme=dark; Path=/', _sessionCookie]);

        expect(store.cookieHeader, 'sabi_session=tok.abc.123');
      },
    );

    test('an empty value clears the session', () async {
      final storage = _MemoryStorage()..value = 'stale';
      final store = SessionCookieStore(storage: storage);
      await store.load();

      await store.capture(['sabi_session=; HttpOnly; Max-Age=0; Path=/']);

      expect(store.hasSession, isFalse);
      expect(storage.value, isNull);
    });

    test('an expiry in the past clears the session', () async {
      final store = SessionCookieStore(storage: _MemoryStorage());

      await store.capture([
        'sabi_session=old; Expires=Wed, 21 Oct 2015 07:28:00 GMT; Path=/',
      ]);

      expect(store.hasSession, isFalse);
    });

    test('an expiry in the future keeps the session', () async {
      final store = SessionCookieStore(storage: _MemoryStorage());

      await store.capture([
        'sabi_session=fresh; Expires=Wed, 21 Oct 2099 07:28:00 GMT; Path=/',
      ]);

      expect(store.hasSession, isTrue);
    });
  });

  group('persistence', () {
    test('a captured token is restored by the next store instance', () async {
      final storage = _MemoryStorage();
      final first = SessionCookieStore(storage: storage);
      await first.capture([_sessionCookie]);

      final second = SessionCookieStore(storage: storage);
      expect(second.hasSession, isFalse);
      await second.load();
      expect(second.cookieHeader, 'sabi_session=tok.abc.123');
    });

    test('a storage read failure reads as signed out', () async {
      final storage = _MemoryStorage()..failRead = true;
      final store = SessionCookieStore(storage: storage);

      await store.load();

      expect(store.hasSession, isFalse);
    });

    test('clear forgets the session in memory and in storage', () async {
      final storage = _MemoryStorage();
      final store = SessionCookieStore(storage: storage);
      await store.capture([_sessionCookie]);

      await store.clear();

      expect(store.hasSession, isFalse);
      expect(storage.value, isNull);
      expect(storage.clears, greaterThan(0));
    });
  });

  group('launch tri-state', () {
    test('a fresh session is unresolved', () {
      expect(SessionStore().isUnresolved, isTrue);
      expect(SessionStore().isAuthenticated, isFalse);
    });

    test('resolving notifies listeners once per transition', () {
      final store = SessionStore();
      var notifications = 0;
      store.addListener(() => notifications++);

      store.resolveAuthenticated();
      store.resolveAuthenticated();
      store.resolveUnauthenticated();

      expect(store.status, SessionStatus.unauthenticated);
      expect(notifications, 2);
    });
  });
}
