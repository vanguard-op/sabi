import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Connectivity state. Defaults online; the UI shows the Offline Banner and
/// disables authorisation when it flips false. A real transport subscription
/// replaces the setter at integration time.
class ConnectivityController extends Notifier<bool> {
  @override
  bool build() => true;

  void setOnline(bool online) => state = online;
}

final connectivityProvider = NotifierProvider<ConnectivityController, bool>(
  ConnectivityController.new,
);
