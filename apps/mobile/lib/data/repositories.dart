import 'package:flutter/foundation.dart';

import '../l10n/sab_strings.dart';
import '../models/account.dart';
import '../models/channel_link.dart';
import '../models/intent_result.dart';
import '../models/payment_method.dart';
import '../models/receipt_summary.dart';
import '../models/service_summary.dart';

/// The account plus the one-time recovery code shown after registration
/// (CONTRACTS.md C-002). The code is single-use.
@immutable
class RegistrationResult {
  const RegistrationResult({required this.account, required this.recoveryCode});

  final Account account;
  final String recoveryCode;
}

/// The account plus whether a new passkey must be enrolled (CONTRACTS.md C-005:
/// `mustEnrolPasskey` is true).
@immutable
class RecoverySignInResult {
  const RecoverySignInResult({
    required this.account,
    this.mustEnrolPasskey = true,
  });

  final Account account;
  final bool mustEnrolPasskey;
}

/// Authentication and onboarding (FEAT-001, CONTRACTS.md C-001–C-007).
///
/// Until the endpoints are live the mock in `mock_repositories.dart` satisfies
/// this shape; the screen never talks to a transport directly.
abstract class AuthRepository {
  /// Whether the device can run a passkey ceremony.
  Future<bool> passkeySupported();

  /// Creates an account and enrols a passkey. When [withPasskey] is false the
  /// caller is on the reduced-security recovery-code path.
  Future<RegistrationResult> createAccount({
    required AppLocale locale,
    required bool withPasskey,
  });

  /// Runs the passkey ceremony and returns the account.
  Future<Account> signInWithPasskey();

  /// Signs in with a recovery code (CONTRACTS.md C-005); the account then needs
  /// a new passkey enrolled.
  Future<RecoverySignInResult> signInWithRecovery(String code);

  Future<void> signOut();
}

/// A catalogue search response (CONTRACTS.md C-010).
@immutable
class CatalogueSearchResult {
  const CatalogueSearchResult({this.results = const [], this.noMatch = false});

  final List<ServiceSummary> results;
  final bool noMatch;
}

/// Intent resolution and service discovery (FEAT-003, FEAT-004; C-009, C-010).
abstract class CatalogueRepository {
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
  });

  Future<CatalogueSearchResult> search(String query);
}

/// The account record (FEAT-001, FEAT-015; C-008).
abstract class AccountRepository {
  Future<Account> me();

  Future<Account> updateLocale(AppLocale locale);

  /// Links a USSD or WhatsApp address to the same account (C-007). Throws
  /// [ChannelAlreadyLinkedException] when another account owns the address.
  Future<ChannelLink> linkChannel({
    required String channel,
    required String address,
  });

  Future<List<PaymentMethod>> paymentMethods();
}

/// Thrown when a channel address belongs to another account.
class ChannelAlreadyLinkedException implements Exception {
  const ChannelAlreadyLinkedException();
}

/// Recent receipts (Phase 2 FEAT-008; not yet contracted, mocked for Home).
abstract class ReceiptRepository {
  Future<List<ReceiptSummary>> recent({int limit = 10});
}
