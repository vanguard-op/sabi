import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Where the session cookie token is kept between app launches.
///
/// A narrow seam so [SessionCookieStore] can be exercised without a platform
/// keystore; production uses [SecureSessionCookieStorage].
abstract class SessionCookieStorage {
  Future<String?> read();

  Future<void> write(String value);

  Future<void> clear();
}

/// Platform secure storage (iOS Keychain, Android encrypted preferences).
class SecureSessionCookieStorage implements SessionCookieStorage {
  const SecureSessionCookieStorage({
    FlutterSecureStorage storage = const FlutterSecureStorage(),
  })
    // A named parameter cannot be private, so the storage is copied to the
    // private field rather than promoted to a public one.
    // ignore: prefer_initializing_formals
    : _storage = storage;

  /// Stored under a name that describes the value, not the transport, so an
  /// inspection of the keystore never implies a plain cookie is kept (NFR-024).
  static const key = 'sabi_session_token';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read() => _storage.read(key: key);

  @override
  Future<void> write(String value) => _storage.write(key: key, value: value);

  @override
  Future<void> clear() => _storage.delete(key: key);
}

/// Holds the session cookie in memory and persists the token in secure storage.
///
/// Native Flutter has no browser cookie jar, so the HttpOnly session cookie set
/// by C-002/C-004 is carried here: [capture] reads a response's `Set-Cookie`,
/// and [cookieHeader] rebuilds the `Cookie` header on later requests. The token
/// is never read out for logging and never leaves this class except as that
/// header (NFR-024). Persisting it is what keeps NFR-026's 30-day session
/// across an app restart (D-039).
class SessionCookieStore {
  SessionCookieStore({SessionCookieStorage? storage})
    : _storage = storage ?? const SecureSessionCookieStorage();

  /// The cookie name the server sets (`session_cookie_name`; C-002/C-004).
  static const cookieName = 'sabi_session';

  final SessionCookieStorage _storage;

  String? _value;
  bool _loaded = false;

  /// Whether a session token is currently held.
  bool get hasSession => _value != null && _value!.isNotEmpty;

  /// Reads the persisted token once. A storage failure reads as signed out:
  /// a payments client fails closed rather than crashing at launch.
  Future<void> load() async {
    if (_loaded) return;
    _loaded = true;
    try {
      final stored = await _storage.read();
      _value = (stored != null && stored.isNotEmpty) ? stored : null;
    } catch (_) {
      _value = null;
    }
  }

  /// The `Cookie` header for an outgoing request, or null when signed out.
  String? get cookieHeader => hasSession ? '$cookieName=$_value' : null;

  /// Captures the session cookie from response `Set-Cookie` headers, persisting
  /// it so the session survives a restart. An empty or expired cookie clears
  /// the stored session.
  Future<void> capture(Iterable<String> setCookieHeaders) async {
    for (final header in setCookieHeaders) {
      final parsed = _parseSetCookie(header);
      if (parsed == null || parsed.name.toLowerCase() != cookieName) continue;
      if (parsed.expired) {
        await clear();
      } else {
        _value = parsed.value;
        _loaded = true;
        await _persist();
      }
      return;
    }
  }

  /// Forgets the session, in memory and in storage. Called on sign-out and when
  /// the gateway definitively rejects the cookie, so a dead cookie is never
  /// resent.
  Future<void> clear() async {
    _loaded = true;
    _value = null;
    try {
      await _storage.clear();
    } catch (_) {
      // A failed delete must not block sign-out; clearing in memory is what
      // stops the dead cookie from being resent this run.
    }
  }

  Future<void> _persist() async {
    try {
      await _storage.write(_value!);
    } catch (_) {
      // A failed write degrades to an in-memory session for this run, which is
      // better than failing an otherwise successful sign-in.
    }
  }

  static const _months = <String, int>{
    'jan': 1,
    'feb': 2,
    'mar': 3,
    'apr': 4,
    'may': 5,
    'jun': 6,
    'jul': 7,
    'aug': 8,
    'sep': 9,
    'oct': 10,
    'nov': 11,
    'dec': 12,
  };

  /// Parses one `Set-Cookie` header into its name, value, and expiry. Only the
  /// session cookie is of interest; the rest of the header is discarded.
  static _ParsedCookie? _parseSetCookie(String header) {
    final segments = header.split(';');
    final pair = segments.first.trim();
    final equals = pair.indexOf('=');
    if (equals <= 0) return null;

    final name = pair.substring(0, equals).trim();
    final value = pair.substring(equals + 1).trim();
    var expired = value.isEmpty;

    for (final segment in segments.skip(1)) {
      final attribute = segment.trim();
      final lower = attribute.toLowerCase();
      if (lower.startsWith('max-age=')) {
        final seconds = int.tryParse(attribute.substring(8).trim());
        if (seconds != null && seconds <= 0) expired = true;
      } else if (lower.startsWith('expires=')) {
        final date = _parseHttpDate(attribute.substring(8).trim());
        if (date != null && !date.isAfter(DateTime.now().toUtc())) {
          expired = true;
        }
      }
    }
    return _ParsedCookie(name: name, value: value, expired: expired);
  }

  /// Parses the RFC 1123 date form used by `Expires`
  /// (e.g. `Wed, 21 Oct 2015 07:28:00 GMT`), returning null for anything else.
  static DateTime? _parseHttpDate(String raw) {
    final match = RegExp(
      r'^(?:[A-Za-z]{3},\s*)?(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+'
      r'(\d{2}):(\d{2}):(\d{2})',
    ).firstMatch(raw);
    if (match == null) return null;
    final month = _months[match.group(2)!.toLowerCase()];
    if (month == null) return null;
    return DateTime.utc(
      int.parse(match.group(3)!),
      month,
      int.parse(match.group(1)!),
      int.parse(match.group(4)!),
      int.parse(match.group(5)!),
      int.parse(match.group(6)!),
    );
  }
}

@immutable
class _ParsedCookie {
  const _ParsedCookie({
    required this.name,
    required this.value,
    required this.expired,
  });

  final String name;
  final String value;
  final bool expired;
}

/// Whether the app knows a live session exists.
enum SessionStatus {
  /// The launch check has not resolved. The router holds on the splash rather
  /// than guessing Welcome or Home and flashing the wrong one.
  unknown,

  /// A persisted session was verified (C-008) or the user signed in.
  authenticated,

  /// No session, or the stored one was rejected. The router shows Welcome.
  unauthenticated,
}

/// Session state for route guarding. A [ChangeNotifier] so go_router can use it
/// directly as `refreshListenable` without rebuilding the router.
class SessionStore extends ChangeNotifier {
  SessionStatus _status = SessionStatus.unknown;

  SessionStatus get status => _status;

  /// True until the launch check settles; the router shows the splash.
  bool get isUnresolved => _status == SessionStatus.unknown;

  bool get isAuthenticated => _status == SessionStatus.authenticated;

  /// Records that a launch check or sign-in found a live session.
  void resolveAuthenticated() => _set(SessionStatus.authenticated);

  /// Records that no live session exists, or the stored one was rejected.
  void resolveUnauthenticated() => _set(SessionStatus.unauthenticated);

  /// The sign-in surfaces' vocabulary; equivalent to [resolveAuthenticated].
  void signIn() => resolveAuthenticated();

  /// The sign-out action; equivalent to [resolveUnauthenticated].
  void signOut() => resolveUnauthenticated();

  void _set(SessionStatus next) {
    if (_status == next) return;
    _status = next;
    notifyListeners();
  }
}
