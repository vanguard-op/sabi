import 'package:flutter/foundation.dart';

/// Session state for route guarding. A [ChangeNotifier] so go_router can use it
/// directly as `refreshListenable` without rebuilding the router.
class SessionStore extends ChangeNotifier {
  bool _authenticated = false;

  bool get isAuthenticated => _authenticated;

  void signIn() {
    if (_authenticated) return;
    _authenticated = true;
    notifyListeners();
  }

  void signOut() {
    if (!_authenticated) return;
    _authenticated = false;
    notifyListeners();
  }
}
