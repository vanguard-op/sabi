import 'package:flutter/foundation.dart';

import '../l10n/sab_strings.dart';
import '../models/account.dart';
import '../models/channel_link.dart';
import '../models/intent_result.dart';
import '../models/payment_case.dart';
import '../models/payment_method.dart';
import '../models/receipt.dart';
import '../models/receipt_summary.dart';
import '../models/service_summary.dart';

/// Thrown when a credential or recovery code is not accepted (C-002/C-004/C-005).
class InvalidCredentialException implements Exception {
  const InvalidCredentialException();
}

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

/// A full catalogue service (CONTRACTS.md C-011 `Service`; schema.md "Service").
///
/// Carries the fields discovery's [ServiceSummary] does not: the service `type`
/// that selects the payment flow, the aliases, and the provider and capability
/// links. Amounts are integer minor units (kobo).
@immutable
class CatalogueService {
  const CatalogueService({
    required this.id,
    required this.type,
    required this.name,
    required this.collectingBody,
    required this.category,
    this.aliases = const [],
    this.providerId,
    this.capabilityId,
    this.knownAmount,
    this.currency = 'NGN',
    this.status = 'active',
    this.refreshedAt,
    this.createdAt,
  });

  final String id;

  /// `government`, `biller`, or `merchant`. Selects the payment flow.
  final String type;
  final String name;
  final String collectingBody;
  final String category;
  final List<String> aliases;
  final String? providerId;
  final String? capabilityId;

  /// Minor units (kobo), or null when the amount is confirmed at payment.
  final int? knownAmount;
  final String currency;

  /// `active`, `unavailable`, or `retired`.
  final String status;
  final DateTime? refreshedAt;
  final DateTime? createdAt;

  bool get hasKnownAmount => knownAmount != null;

  factory CatalogueService.fromJson(Map<String, dynamic> json) =>
      CatalogueService(
        id: (json['id'] ?? json['serviceId'] ?? '').toString(),
        type: (json['type'] ?? '').toString(),
        name: (json['name'] ?? '').toString(),
        collectingBody: (json['collectingBody'] ?? '').toString(),
        category: (json['category'] ?? '').toString(),
        aliases: (json['aliases'] as List? ?? const [])
            .map((e) => e.toString())
            .toList(growable: false),
        providerId: json['providerId']?.toString(),
        capabilityId: json['capabilityId']?.toString(),
        knownAmount: (json['knownAmount'] as num?)?.toInt(),
        currency: (json['currency'] ?? 'NGN').toString(),
        status: (json['status'] ?? 'active').toString(),
        refreshedAt: _parseOptionalTime(json['refreshedAt']),
        createdAt: _parseOptionalTime(json['createdAt']),
      );
}

DateTime? _parseOptionalTime(Object? raw) {
  final text = raw?.toString();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text)?.toUtc();
}

/// A `404` from the service-detail endpoint: the service is unknown (C-011).
class ServiceNotFoundException implements Exception {
  const ServiceNotFoundException();
}

/// Intent resolution and service discovery (FEAT-003, FEAT-004; C-009, C-010).
///
/// Service detail (C-011) backs the payment surface: the confirmation resolves
/// the service it is about to pay from the catalogue rather than a hardcoded
/// sandbox entry.
abstract class CatalogueRepository {
  /// Resolves a free-form request. [history] carries the prior conversation,
  /// oldest first, bounded to [intentHistoryMaxEntries] and omitted from the
  /// wire when empty (C-009).
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
    List<IntentHistoryTurn> history = const [],
  });

  Future<CatalogueSearchResult> search(String query);

  /// Fetches one service by id (C-011). Throws [ServiceNotFoundException] when
  /// the catalogue has no such service.
  Future<CatalogueService> serviceDetail(String serviceId);
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

/// Recent receipts for Home (FEAT-008).
abstract class ReceiptRepository {
  Future<List<ReceiptSummary>> recent({int limit = 10});
}

/// A page of receipts plus the cursor for the next one (C-023). A null cursor
/// means the end of the history.
@immutable
class ReceiptPage {
  const ReceiptPage({required this.receipts, this.nextCursor});

  final List<ReceiptSummary> receipts;
  final String? nextCursor;

  bool get hasMore => nextCursor != null;
}

/// A page of cases plus the cursor for the next one (C-026).
@immutable
class CasePage {
  const CasePage({required this.cases, this.nextCursor});

  final List<CaseSummary> cases;
  final String? nextCursor;

  bool get hasMore => nextCursor != null;
}

/// A case as returned by the list endpoint (C-026).
@immutable
class CaseSummary {
  const CaseSummary({
    required this.caseId,
    required this.paymentId,
    required this.type,
    required this.status,
    required this.openedAt,
    required this.updatedAt,
  });

  final String caseId;
  final String paymentId;
  final CaseType type;
  final CaseStatus status;
  final DateTime openedAt;
  final DateTime updatedAt;

  factory CaseSummary.fromJson(Map<String, dynamic> json) => CaseSummary(
    caseId: json['caseId'].toString(),
    paymentId: json['paymentId'].toString(),
    type: CaseType.parse((json['type'] ?? 'failed_no_delivery').toString()),
    status: CaseStatus.parse((json['status'] ?? 'open').toString()),
    openedAt:
        DateTime.tryParse(json['openedAt']?.toString() ?? '') ?? DateTime(0),
    updatedAt:
        DateTime.tryParse(json['updatedAt']?.toString() ?? '') ?? DateTime(0),
  );
}

/// Receipt retrieval (FEAT-008; C-023, C-024, C-025). Every method is scoped to
/// the authenticated account owner; the screen depends on this abstraction, not
/// on a transport.
abstract class ReceiptsRepository {
  /// Lists the owner's receipts, newest first, optionally filtered by [query]
  /// across reference, payee, and date (C-023).
  Future<ReceiptPage> list({String? query, String? cursor, int limit = 20});

  /// Fetches one receipt with the payment it proves (C-024).
  Future<ReceiptDetail> detail(String receiptId);

  /// Fetches the stored document behind a receipt, for export or share
  /// (C-025). Throws [ReceiptDocumentPendingException] while the source
  /// document is still being written.
  Future<ReceiptDocument> document(String receiptId);
}

/// Thrown when a receipt's source document has not arrived yet (C-025 409).
class ReceiptDocumentPendingException implements Exception {
  const ReceiptDocumentPendingException();
}

/// Thrown when a receipt is not found or not owned by the account (C-024/C-025).
class ReceiptNotFoundException implements Exception {
  const ReceiptNotFoundException();
}

/// A `409` from a refund: the reference was already refunded (FEAT-009).
class DuplicateRefundException implements Exception {
  const DuplicateRefundException();
}

/// A `422` from a refund: the payment is not refundable in its current state.
class RefundNotAllowedException implements Exception {
  const RefundNotAllowedException();
}

/// The result of initiating a refund (C-029). Status is `reversed` or
/// `refunded`.
@immutable
class RefundResult {
  const RefundResult({
    required this.paymentId,
    required this.status,
    this.refundReference,
  });

  final String paymentId;
  final String status;
  final String? refundReference;

  factory RefundResult.fromJson(Map<String, dynamic> json) => RefundResult(
    paymentId: json['paymentId'].toString(),
    status: json['status'].toString(),
    refundReference: json['refundReference']?.toString(),
  );
}

/// Payment status, failure, and refund handling (FEAT-009; C-026–C-029).
abstract class CasesRepository {
  /// Lists the owner's cases, optionally filtered by [status] (C-026).
  Future<CasePage> list({String? status, String? cursor, int limit = 20});

  /// Fetches one case with its payment and timeline (C-027).
  Future<CaseDetail> detail(String caseId);

  /// Opens a dispute on a case (C-028). Throws [DuplicateDisputeException] when
  /// a dispute already exists for the payment.
  Future<CaseSummary> dispute({required String caseId, required String reason});

  /// Requests a refund for a payment (C-029). The caller supplies the
  /// idempotency key so a retry is never a second refund.
  Future<RefundResult> refund({
    required String paymentId,
    required String reason,
    required String idempotencyKey,
  });
}

/// Thrown when a dispute already exists for the payment (C-028 409).
class DuplicateDisputeException implements Exception {
  const DuplicateDisputeException();
}

/// Thrown when a case or payment is not found or not owned (C-027/C-029).
class CaseNotFoundException implements Exception {
  const CaseNotFoundException();
}
