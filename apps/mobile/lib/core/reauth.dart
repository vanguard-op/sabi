import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Marks that a session expired mid-use so the shared Re-authorisation overlay
/// can block the surface and preserve its state until re-authenticated.
class ReauthController extends Notifier<bool> {
  @override
  bool build() => false;

  void require() => state = true;

  void resolve() => state = false;
}

final reauthProvider = NotifierProvider<ReauthController, bool>(
  ReauthController.new,
);
