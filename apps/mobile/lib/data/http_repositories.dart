import '../core/api_client.dart';
import '../core/api_exception.dart';
import '../l10n/sab_strings.dart';
import '../models/account.dart';
import '../models/channel_link.dart';
import '../models/intent_result.dart';
import '../models/payment_case.dart';
import '../models/payment_method.dart';
import '../models/receipt.dart';
import '../models/receipt_summary.dart';
import '../models/service_summary.dart';
import 'repositories.dart';

/// Live catalogue and intent resolution against the gateway (FEAT-003,
/// FEAT-004; C-009, C-010).
class HttpCatalogueRepository implements CatalogueRepository {
  HttpCatalogueRepository(this._api);

  final SabApiClient _api;

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
  }) async {
    try {
      final body = await _api.post(
        '/agent/intents',
        body: {'text': text, 'locale': locale.code, 'channel': 'app'},
      );
      // The envelope carries the intent, its candidates, and `source` as
      // siblings; fold them into the one model the surface renders so a
      // fallback resolution stays visible and must be confirmed before money
      // moves (C-009).
      return IntentResult.fromJson({
        ...Map<String, dynamic>.from(body['intent'] as Map? ?? {}),
        'candidates': body['candidates'] ?? const [],
        'source': body['source'],
      });
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<CatalogueSearchResult> search(String query) async {
    try {
      final body = await _api.get(
        '/catalogue/search',
        query: {'q': query},
      );
      final results = (body['results'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => ServiceSummary.fromJson(e.cast<String, dynamic>()))
          .toList(growable: false);
      return CatalogueSearchResult(
        results: results,
        noMatch: body['noMatch'] == true || results.isEmpty,
      );
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<CatalogueService> serviceDetail(String serviceId) async {
    try {
      final body = await _api.get('/catalogue/services/$serviceId');
      final service = body['service'];
      if (service is! Map) {
        throw const ApiServerFailure('The service could not be loaded.');
      }
      return CatalogueService.fromJson(service.cast<String, dynamic>());
    } on ApiNotFound {
      // C-011 404: the catalogue has no such service.
      throw const ServiceNotFoundException();
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }
}

/// Live account record (FEAT-001, FEAT-015; C-007, C-008).
class HttpAccountRepository implements AccountRepository {
  HttpAccountRepository(this._api);

  final SabApiClient _api;

  @override
  Future<Account> me() async {
    try {
      final body = await _api.get('/account/me');
      return Account.fromJson(body);
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<Account> updateLocale(AppLocale locale) async {
    // No contract exposes an end-user locale update yet; the account's locale is
    // set at registration. Return the authoritative record so the screen reflects
    // the server, not an optimistic local write. The client-side locale switch is
    // driven by the l10n provider, independent of this call.
    return me();
  }

  @override
  Future<ChannelLink> linkChannel({
    required String channel,
    required String address,
  }) async {
    try {
      final body = await _api.post(
        '/auth/channel-links',
        body: {'channel': channel, 'address': address.trim()},
      );
      return ChannelLink.fromJson(body);
    } on ApiConflict {
      // C-007 409: the address already belongs to another account.
      throw const ChannelAlreadyLinkedException();
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<List<PaymentMethod>> paymentMethods() async {
    // No contract exposes saved payment methods yet; an empty list is the honest
    // answer rather than a fabricated rail. The Account surface already renders
    // an empty state for this.
    return const <PaymentMethod>[];
  }
}

/// Live recent receipts for Home (FEAT-008; C-023). Home asks only for the
/// newest few, so this lists and takes the head.
class HttpReceiptRepository implements ReceiptRepository {
  HttpReceiptRepository(this._api);

  final SabApiClient _api;

  @override
  Future<List<ReceiptSummary>> recent({int limit = 10}) async {
    try {
      final body = await _api.get('/receipts', query: {'limit': '$limit'});
      return (body['receipts'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => _summary(e.cast<String, dynamic>()))
          .toList(growable: false);
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  /// Maps the contract's `ReceiptSummary` (`receiptId`, `issuedAt` nullable,
  /// `kind` as a wire token) to the display shape the Home list uses.
  static ReceiptSummary _summary(Map<String, dynamic> json) => ReceiptSummary(
    id: json['receiptId'].toString(),
    reference: json['reference']?.toString() ?? '',
    payee: json['payee']?.toString() ?? '',
    amount: (json['amount'] as num?)?.toInt() ?? 0,
    currency: (json['currency'] ?? 'NGN').toString(),
    issuedAt:
        DateTime.tryParse(json['issuedAt']?.toString() ?? '') ?? DateTime(0),
    kind: _kindLabel((json['kind'] ?? 'biller_confirmation').toString()),
    status: _listStatus((json['status'] ?? '').toString()),
  );

  static String _kindLabel(String wire) => switch (wire) {
    'official_e_receipt' || 'officialEReceipt' => 'Official receipt',
    'token' => 'Token',
    _ => 'Biller confirmation',
  };

  /// The contract `status` on a receipt summary is the payment status
  /// (settled/pending/failed); `awaiting_receipt` is its own display state.
  static PaymentStatus _listStatus(String wire) => PaymentStatus.parse(wire);
}

/// Live receipts retrieval (FEAT-008; C-023–C-025).
class HttpReceiptsRepository implements ReceiptsRepository {
  HttpReceiptsRepository(this._api);

  final SabApiClient _api;

  @override
  Future<ReceiptPage> list({String? query, String? cursor, int limit = 20}) async {
    try {
      final body = await _api.get(
        '/receipts',
        query: {
          'q': (query == null || query.isEmpty) ? null : query,
          'cursor': cursor,
          'limit': '$limit',
        },
      );
      final receipts = (body['receipts'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => HttpReceiptRepository._summary(e.cast<String, dynamic>()))
          .toList(growable: false);
      return ReceiptPage(
        receipts: receipts,
        nextCursor: body['nextCursor']?.toString(),
      );
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<ReceiptDetail> detail(String receiptId) async {
    try {
      final body = await _api.get('/receipts/$receiptId');
      return ReceiptDetail.fromJson(body);
    } on ApiNotFound {
      throw const ReceiptNotFoundException();
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<ReceiptDocument> document(String receiptId) async {
    try {
      final body = await _api.get('/receipts/$receiptId/document');
      return ReceiptDocument.fromJson(body);
    } on ApiConflict {
      // C-025 409: the source document has not been written yet.
      throw const ReceiptDocumentPendingException();
    } on ApiNotFound {
      throw const ReceiptNotFoundException();
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }
}

/// Live case retrieval (FEAT-009; C-026–C-029).
class HttpCasesRepository implements CasesRepository {
  HttpCasesRepository(this._api);

  final SabApiClient _api;

  @override
  Future<CasePage> list({String? status, String? cursor, int limit = 20}) async {
    try {
      final body = await _api.get(
        '/cases',
        query: {
          'status': (status == null || status.isEmpty) ? null : status,
          'cursor': cursor,
          'limit': '$limit',
        },
      );
      final cases = (body['cases'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => CaseSummary.fromJson(e.cast<String, dynamic>()))
          .toList(growable: false);
      return CasePage(cases: cases, nextCursor: body['nextCursor']?.toString());
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<CaseDetail> detail(String caseId) async {
    try {
      final body = await _api.get('/cases/$caseId');
      return CaseDetail.fromJson(body);
    } on ApiNotFound {
      throw const CaseNotFoundException();
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<CaseSummary> dispute({
    required String caseId,
    required String reason,
  }) async {
    try {
      final body = await _api.post(
        '/cases/$caseId/dispute',
        body: {'reason': reason},
      );
      return CaseSummary(
        caseId: body['caseId'].toString(),
        paymentId: '',
        type: CaseType.disputed,
        status: CaseStatus.parse((body['status'] ?? 'open').toString()),
        openedAt: DateTime.tryParse(body['openedAt']?.toString() ?? '') ??
            DateTime(0),
        updatedAt: DateTime.tryParse(body['openedAt']?.toString() ?? '') ??
            DateTime(0),
      );
    } on ApiConflict {
      throw const DuplicateDisputeException();
    } on ApiNotFound {
      throw const CaseNotFoundException();
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<RefundResult> refund({
    required String paymentId,
    required String reason,
    required String idempotencyKey,
  }) async {
    try {
      final body = await _api.post(
        '/payments/$paymentId/refund',
        body: {'reason': reason},
        headers: {'Idempotency-Key': idempotencyKey},
      );
      return RefundResult.fromJson(body);
    } on ApiNotFound {
      throw const CaseNotFoundException();
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiConflict {
      // C-029 409: a refund for this reference already exists.
      throw const DuplicateRefundException();
    } on ApiException catch (e) {
      if (e.statusCode == 422) {
        // C-029 422: the payment is not refundable in its current state.
        throw const RefundNotAllowedException();
      }
      throw ApiServerFailure(e.message);
    }
  }
}
