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

const Duration _defaultLatency = Duration(milliseconds: 350);

/// Mock authentication for the foundation build. A device without a passkey is
/// simulated by construction, so the reduced-security path is exercisable.
class MockAuthRepository implements AuthRepository {
  MockAuthRepository({
    this.passkeyAvailable = true,
    this.latency = _defaultLatency,
    this.failNextCreate = false,
    this.failNextSignIn = false,
  });

  bool passkeyAvailable;
  Duration latency;
  bool failNextCreate;
  bool failNextSignIn;

  @override
  Future<bool> passkeySupported() async {
    await Future<void>.delayed(latency);
    return passkeyAvailable;
  }

  @override
  Future<RegistrationResult> createAccount({
    required AppLocale locale,
    required bool withPasskey,
  }) async {
    await Future<void>.delayed(latency);
    if (failNextCreate) {
      failNextCreate = false;
      throw const InvalidCredentialException();
    }
    return RegistrationResult(
      account: Account(
        id: 'acct_mock_0001',
        displayName: null,
        locale: locale.code,
        preferredChannel: withPasskey ? 'app' : 'ussd',
        kycStatus: VerificationStatus.unverified,
        accountStatus: 'active',
        createdAt: DateTime.utc(2026, 10, 1),
        updatedAt: DateTime.utc(2026, 10, 1),
      ),
      recoveryCode: 'SABI-4F9K-2Q7M-88XD',
    );
  }

  @override
  Future<Account> signInWithPasskey() async {
    await Future<void>.delayed(latency);
    if (failNextSignIn) {
      failNextSignIn = false;
      throw const InvalidCredentialException();
    }
    return _existingAccount();
  }

  @override
  Future<RecoverySignInResult> signInWithRecovery(String code) async {
    await Future<void>.delayed(latency);
    if (code.trim().length < 8) {
      throw const InvalidCredentialException();
    }
    return RecoverySignInResult(account: _existingAccount());
  }

  @override
  Future<void> signOut() async {
    await Future<void>.delayed(latency);
  }

  Account _existingAccount() => Account(
    id: 'acct_mock_0001',
    displayName: 'Ngozi',
    locale: AppLocale.english.code,
    preferredChannel: 'app',
    kycStatus: VerificationStatus.unverified,
    accountStatus: 'active',
    createdAt: DateTime.utc(2026, 10, 1),
    updatedAt: DateTime.utc(2026, 10, 1),
  );
}

/// Mock intent resolution and catalogue search. The text patterns map to the
/// Home states the screens document so each can be exercised without a model.
class MockCatalogueRepository implements CatalogueRepository {
  MockCatalogueRepository({this.latency = _defaultLatency});

  Duration latency;
  bool failNext = false;

  static const _landUse = ServiceSummary(
    serviceId: 'svc_lagos_land_use',
    name: 'Land Use Charge',
    collectingBody: 'Lagos State Government',
    category: 'Government',
    knownAmount: 2500000,
    confidence: 0.94,
  );

  @override
  Future<IntentResult> resolveIntent({
    required String text,
    required AppLocale locale,
  }) async {
    await Future<void>.delayed(latency);
    if (failNext) {
      failNext = false;
      throw const InvalidCredentialException();
    }
    final q = text.toLowerCase();
    if (q.contains('land use') || q.contains('land')) {
      return IntentResult(
        intentType: 'bill_payment',
        target: 'Lagos State Government',
        amount: 2500000,
        reference: 'LUC-2026-0001',
        confidence: 0.94,
        language: locale.code,
        candidates: const [_landUse],
      );
    }
    if (q.contains('council') || q.contains('levy')) {
      return IntentResult(
        intentType: 'bill_payment',
        target: 'Council levy',
        confidence: 0.8,
        language: locale.code,
        candidates: const [
          ServiceSummary(
            serviceId: 'svc_onitsha_council',
            name: 'Council levy',
            collectingBody: 'Onitsha North LGA',
            category: 'Government',
            confidence: 0.8,
          ),
          ServiceSummary(
            serviceId: 'svc_onitsha_south',
            name: 'Council levy',
            collectingBody: 'Onitsha South LGA',
            category: 'Government',
            confidence: 0.62,
          ),
          ServiceSummary(
            serviceId: 'svc_awka_council',
            name: 'Council levy',
            collectingBody: 'Awka South LGA',
            category: 'Government',
            confidence: 0.51,
          ),
        ],
      );
    }
    if (q.contains('electric') || q.contains('light') || q.contains('nepa')) {
      return IntentResult(
        intentType: 'bill_payment',
        target: 'Electricity',
        confidence: 0.45,
        language: locale.code,
        clarifyingQuestion: 'Which electricity provider do you pay?',
        candidates: const [
          ServiceSummary(
            serviceId: 'svc_ikeja_electric',
            name: 'Electricity token',
            collectingBody: 'Ikeja Electric',
            category: 'Biller',
            confidence: 0.45,
          ),
          ServiceSummary(
            serviceId: 'svc_ekedc',
            name: 'Electricity token',
            collectingBody: 'Eko Electricity (EKEDC)',
            category: 'Biller',
            confidence: 0.41,
          ),
        ],
      );
    }
    if (q.contains('school') || q.contains('xyz')) {
      return IntentResult(
        intentType: 'unresolved',
        confidence: 0.18,
        language: locale.code,
      );
    }
    return IntentResult(
      intentType: 'bill_payment',
      target: 'MTN',
      confidence: 0.88,
      language: locale.code,
      candidates: const [
        ServiceSummary(
          serviceId: 'svc_mtn_airtime',
          name: 'Airtime top-up',
          collectingBody: 'MTN Nigeria',
          category: 'Biller',
          confidence: 0.88,
        ),
      ],
    );
  }

  @override
  Future<CatalogueSearchResult> search(String query) async {
    await Future<void>.delayed(latency);
    final result = await resolveIntent(text: query, locale: AppLocale.english);
    return CatalogueSearchResult(
      results: result.candidates,
      noMatch: result.candidates.isEmpty,
    );
  }
}

/// Mock account record. Status and channel links are mutable so Account's
/// states can be demonstrated and tested.
class MockAccountRepository implements AccountRepository {
  MockAccountRepository({
    this.latency = _defaultLatency,
    this.kycStatus = VerificationStatus.unverified,
    this.accountStatus = 'active',
    List<ChannelLink> channelLinks = const [],
    this.paymentMethodsList = const [],
  }) : _channelLinks = [...channelLinks];

  Duration latency;
  VerificationStatus kycStatus;
  String accountStatus;
  AppLocale locale = AppLocale.english;
  final List<ChannelLink> _channelLinks;
  List<PaymentMethod> paymentMethodsList;

  @override
  Future<Account> me() async {
    await Future<void>.delayed(latency);
    return Account(
      id: 'acct_mock_0001',
      displayName: 'Ngozi',
      locale: locale.code,
      preferredChannel: 'app',
      kycStatus: kycStatus,
      accountStatus: accountStatus,
      channelLinks: List.unmodifiable(_channelLinks),
      createdAt: DateTime.utc(2026, 10, 1),
      updatedAt: DateTime.utc(2026, 10, 1),
    );
  }

  @override
  Future<Account> updateLocale(AppLocale value) async {
    await Future<void>.delayed(latency);
    locale = value;
    return me();
  }

  @override
  Future<ChannelLink> linkChannel({
    required String channel,
    required String address,
  }) async {
    await Future<void>.delayed(latency);
    if (address.trim() == '08000000000') {
      throw const ChannelAlreadyLinkedException();
    }
    final link = ChannelLink(
      id: 'link_${_channelLinks.length + 1}',
      channel: channel,
      address: address.trim(),
    );
    _channelLinks.add(link);
    return link;
  }

  @override
  Future<List<PaymentMethod>> paymentMethods() async {
    await Future<void>.delayed(latency);
    return List.unmodifiable(paymentMethodsList);
  }
}

/// Mock recent receipts (Phase 2 data; enough to exercise Home and Receipts).
class MockReceiptRepository implements ReceiptRepository {
  MockReceiptRepository({
    this.latency = _defaultLatency,
    List<ReceiptSummary>? receipts,
  }) : _receipts = receipts ?? _seed();

  Duration latency;
  final List<ReceiptSummary> _receipts;

  static List<ReceiptSummary> _seed() => [
    ReceiptSummary(
      id: 'rcp_1',
      reference: 'LUC-2026-0001',
      payee: 'Lagos State Government',
      amount: 2500000,
      currency: 'NGN',
      kind: 'Government',
      status: PaymentStatus.settled,
      issuedAt: DateTime.utc(2026, 9, 28, 10, 30),
    ),
    ReceiptSummary(
      id: 'rcp_2',
      reference: 'MTN-2026-4410',
      payee: 'MTN Nigeria',
      amount: 200000,
      currency: 'NGN',
      kind: 'Biller',
      status: PaymentStatus.pending,
      issuedAt: DateTime.utc(2026, 9, 26, 8, 5),
    ),
  ];

  @override
  Future<List<ReceiptSummary>> recent({int limit = 10}) async {
    await Future<void>.delayed(latency);
    return _receipts.take(limit).toList(growable: false);
  }
}

/// A cursor-based page over an in-memory list, shared by the receipt and case
/// mocks so both servers page the same way the contracts do.
class _CursorList<T> {
  const _CursorList(this.items);

  final List<T> items;

  ({List<T> page, String? nextCursor}) page(String? cursor, int limit) {
    final start = cursor == null ? 0 : int.tryParse(cursor) ?? 0;
    final end = (start + limit).clamp(0, items.length);
    final page = items.sublist(start.clamp(0, items.length), end);
    return (
      page: page,
      nextCursor: end < items.length ? end.toString() : null,
    );
  }
}

/// Mock receipt retrieval (FEAT-008; C-023–C-025). The seed spans several
/// months and all three verification states so every Receipts and Receipt
/// Detail state is reachable without a live endpoint.
class MockReceiptsRepository implements ReceiptsRepository {
  MockReceiptsRepository({
    this.latency = _defaultLatency,
    List<ReceiptDetail>? details,
  }) : _details = details ?? _seed();

  Duration latency;
  bool failNextList = false;
  bool failNextDetail = false;

  final List<ReceiptDetail> _details;

  static List<ReceiptDetail> _seed() => [
    _detail(
      id: 'rcp_1',
      paymentId: 'pay_1',
      reference: 'LUC-2026-0001',
      payee: 'Lagos State Government',
      amount: 2500000,
      kind: ReceiptKind.officialEReceipt,
      verification: ReceiptVerification.verified,
      receiptNumber: 'FTeR-2026-000123',
      issuedAt: DateTime.utc(2026, 9, 28, 10, 30),
      createdAt: DateTime.utc(2026, 9, 28, 10, 31),
      paymentStatus: 'succeeded',
    ),
    _detail(
      id: 'rcp_2',
      paymentId: 'pay_2',
      reference: 'MTN-2026-4410',
      payee: 'MTN Nigeria',
      amount: 200000,
      kind: ReceiptKind.billerConfirmation,
      verification: ReceiptVerification.pending,
      issuedAt: DateTime.utc(2026, 9, 26, 8, 5),
      createdAt: DateTime.utc(2026, 9, 26, 8, 6),
      paymentStatus: 'succeeded',
    ),
    _detail(
      id: 'rcp_3',
      paymentId: 'pay_3',
      reference: 'EKEDC-2026-7781',
      payee: 'Eko Electricity (EKEDC)',
      amount: 750000,
      kind: ReceiptKind.token,
      verification: ReceiptVerification.unverified,
      unverifiedReason: 'The biller has not confirmed this receipt yet.',
      issuedAt: DateTime.utc(2026, 8, 30, 14, 20),
      createdAt: DateTime.utc(2026, 8, 30, 14, 21),
      paymentStatus: 'succeeded',
    ),
    _detail(
      id: 'rcp_4',
      paymentId: 'pay_4',
      reference: 'LUC-2026-000099',
      payee: 'Lagos State Government',
      amount: 1800000,
      kind: ReceiptKind.officialEReceipt,
      verification: ReceiptVerification.verified,
      receiptNumber: 'FTeR-2026-000099',
      issuedAt: DateTime.utc(2026, 7, 18, 9, 15),
      createdAt: DateTime.utc(2026, 7, 18, 9, 16),
      paymentStatus: 'succeeded',
    ),
  ];

  static ReceiptDetail _detail({
    required String id,
    required String paymentId,
    required String reference,
    required String payee,
    required int amount,
    required ReceiptKind kind,
    required ReceiptVerification verification,
    required DateTime issuedAt,
    required DateTime createdAt,
    required String paymentStatus,
    String? receiptNumber,
    String? unverifiedReason,
  }) => ReceiptDetail(
    receipt: Receipt(
      id: id,
      paymentId: paymentId,
      kind: kind,
      receiptNumber: receiptNumber,
      verificationStatus: verification,
      unverifiedReason: unverifiedReason,
      documentRef: 'docs/$id.pdf',
      issuedAt: issuedAt,
      createdAt: createdAt,
    ),
    payment: ReceiptPayment(
      paymentId: paymentId,
      serviceId: 'svc_$payee',
      amount: amount,
      currency: 'NGN',
      payee: payee,
      status: paymentStatus,
      channel: 'app',
      createdAt: createdAt,
      updatedAt: createdAt,
    ),
  );

  @override
  Future<ReceiptPage> list({
    String? query,
    String? cursor,
    int limit = 20,
  }) async {
    await Future<void>.delayed(latency);
    if (failNextList) {
      failNextList = false;
      throw const InvalidCredentialException();
    }
    final q = query?.trim().toLowerCase();
    final matched = q == null || q.isEmpty
        ? _details
        : _details.where((d) {
            final date = d.receipt.issuedAt ?? d.receipt.createdAt;
            final formatted = '${date.year}-${date.month}-${date.day}';
            return d.payment.payee.toLowerCase().contains(q) ||
                d.receipt.id.toLowerCase().contains(q) ||
                d.payment.paymentId.toLowerCase().contains(q) ||
                formatted.contains(q) ||
                _referenceOf(d).toLowerCase().contains(q);
          }).toList(growable: false);
    final paged = _CursorList(matched).page(cursor, limit);
    return ReceiptPage(
      receipts: paged.page.map(_summaryOf).toList(growable: false),
      nextCursor: paged.nextCursor,
    );
  }

  @override
  Future<ReceiptDetail> detail(String receiptId) async {
    await Future<void>.delayed(latency);
    if (failNextDetail) {
      failNextDetail = false;
      throw const InvalidCredentialException();
    }
    final found = _details
        .where((d) => d.receipt.id == receiptId)
        .firstOrNull;
    if (found == null) throw const ReceiptNotFoundException();
    return found;
  }

  @override
  Future<ReceiptDocument> document(String receiptId) async {
    await Future<void>.delayed(latency);
    final found = _details
        .where((d) => d.receipt.id == receiptId)
        .firstOrNull;
    if (found == null) throw const ReceiptNotFoundException();
    if (found.receipt.verificationStatus == ReceiptVerification.pending) {
      throw const ReceiptDocumentPendingException();
    }
    return ReceiptDocument(
      documentRef: found.receipt.documentRef,
      contentType: 'application/pdf',
      shareToken: 'shr_${found.receipt.id}',
    );
  }

  static String _referenceOf(ReceiptDetail d) => switch (d.receipt.id) {
    'rcp_1' => 'LUC-2026-0001',
    'rcp_2' => 'MTN-2026-4410',
    'rcp_3' => 'EKEDC-2026-7781',
    'rcp_4' => 'LUC-2026-000099',
    _ => d.payment.paymentId,
  };

  static ReceiptSummary _summaryOf(ReceiptDetail d) => ReceiptSummary(
    id: d.receipt.id,
    reference: _referenceOf(d),
    payee: d.payment.payee,
    amount: d.payment.amount,
    currency: d.payment.currency,
    issuedAt: d.receipt.issuedAt ?? d.receipt.createdAt,
    kind: _kindLabel(d.receipt.kind),
    status: switch (d.receipt.verificationStatus) {
      ReceiptVerification.verified => PaymentStatus.settled,
      ReceiptVerification.unverified => PaymentStatus.failed,
      ReceiptVerification.pending => PaymentStatus.awaitingReceipt,
    },
  );

  static String _kindLabel(ReceiptKind kind) => switch (kind) {
    ReceiptKind.officialEReceipt => 'Official receipt',
    ReceiptKind.billerConfirmation => 'Biller confirmation',
    ReceiptKind.token => 'Token',
  };
}

/// Mock payment cases (FEAT-009; C-026–C-029). The seed exercises every case
/// state on screen 8 plus a resolved case with a full timeline.
class MockCasesRepository implements CasesRepository {
  MockCasesRepository({
    this.latency = _defaultLatency,
    List<CaseDetail>? cases,
  }) : _cases = cases ?? _seed();

  Duration latency;
  bool failNextDetail = false;
  bool failNextRefund = false;

  final List<CaseDetail> _cases;

  static List<CaseDetail> _seed() => [
    _detail(
      id: 'case_1',
      paymentId: 'pay_failed_1',
      type: CaseType.failedNoDelivery,
      status: CaseStatus.awaitingProvider,
      payee: 'Ikeja Electric',
      amount: 500000,
      paymentStatus: 'failed',
      openedAt: DateTime.utc(2026, 9, 29, 11, 0),
      updatedAt: DateTime.utc(2026, 9, 30, 9, 0),
      failureReason: 'The biller did not confirm the token.',
    ),
    _detail(
      id: 'case_2',
      paymentId: 'pay_refund_1',
      type: CaseType.refund,
      status: CaseStatus.open,
      payee: 'MTN Nigeria',
      amount: 300000,
      paymentStatus: 'reversed',
      openedAt: DateTime.utc(2026, 9, 27, 16, 30),
      updatedAt: DateTime.utc(2026, 9, 27, 16, 35),
    ),
    _detail(
      id: 'case_3',
      paymentId: 'pay_reconcile_1',
      type: CaseType.failedNoDelivery,
      status: CaseStatus.open,
      payee: 'Eko Electricity (EKEDC)',
      amount: 820000,
      paymentStatus: 'failed',
      openedAt: DateTime.utc(2026, 9, 25, 13, 10),
      updatedAt: DateTime.utc(2026, 9, 25, 13, 12),
      failureReason: 'The rail and the biller disagree.',
    ),
    _detail(
      id: 'case_4',
      paymentId: 'pay_escalated_1',
      type: CaseType.failedNoDelivery,
      status: CaseStatus.escalated,
      payee: 'Lagos State Government',
      amount: 1200000,
      paymentStatus: 'failed',
      openedAt: DateTime.utc(2026, 9, 20, 10, 0),
      updatedAt: DateTime.utc(2026, 9, 24, 10, 0),
    ),
    _detail(
      id: 'case_5',
      paymentId: 'pay_resolved_1',
      type: CaseType.refund,
      status: CaseStatus.resolved,
      payee: 'MTN Nigeria',
      amount: 150000,
      paymentStatus: 'refunded',
      openedAt: DateTime.utc(2026, 9, 10, 8, 0),
      updatedAt: DateTime.utc(2026, 9, 13, 8, 0),
      resolvedAt: DateTime.utc(2026, 9, 13, 8, 0),
    ),
  ];

  static CaseDetail _detail({
    required String id,
    required String paymentId,
    required CaseType type,
    required CaseStatus status,
    required String payee,
    required int amount,
    required String paymentStatus,
    required DateTime openedAt,
    required DateTime updatedAt,
    DateTime? resolvedAt,
    String? failureReason,
  }) => CaseDetail(
    paymentCase: PaymentCase(
      id: id,
      paymentId: paymentId,
      type: type,
      status: status,
      assigneeRole: 'support_operations_agent',
      openedAt: openedAt,
      updatedAt: updatedAt,
      resolvedAt: resolvedAt,
    ),
    payment: CasePayment(
      paymentId: paymentId,
      serviceId: 'svc_case',
      amount: amount,
      currency: 'NGN',
      payee: payee,
      status: paymentStatus,
      channel: 'app',
      createdAt: openedAt,
      updatedAt: updatedAt,
      failureReason: failureReason,
    ),
    timeline: [
      PaymentEvent(
        id: '${id}_ev_2',
        paymentId: paymentId,
        status: paymentStatus,
        actor: status == CaseStatus.resolved ? 'system' : 'provider',
        detail: status == CaseStatus.resolved
            ? 'Refund settled.'
            : 'Case updated.',
        occurredAt: updatedAt,
        createdAt: updatedAt,
      ),
      PaymentEvent(
        id: '${id}_ev_1',
        paymentId: paymentId,
        status: 'failed',
        actor: 'system',
        detail: failureReason,
        occurredAt: openedAt,
        createdAt: openedAt,
      ),
    ],
  );

  @override
  Future<CasePage> list({String? status, String? cursor, int limit = 20}) async {
    await Future<void>.delayed(latency);
    final filtered = status == null || status.isEmpty
        ? _cases
        : _cases
              .where((c) => c.paymentCase.status.wire == status)
              .toList(growable: false);
    final paged = _CursorList(filtered).page(cursor, limit);
    return CasePage(
      cases: paged.page.map(_summaryOf).toList(growable: false),
      nextCursor: paged.nextCursor,
    );
  }

  @override
  Future<CaseDetail> detail(String caseId) async {
    await Future<void>.delayed(latency);
    if (failNextDetail) {
      failNextDetail = false;
      throw const InvalidCredentialException();
    }
    final found = _cases
        .where((c) => c.paymentCase.id == caseId)
        .firstOrNull;
    if (found == null) throw const CaseNotFoundException();
    return found;
  }

  @override
  Future<CaseSummary> dispute({
    required String caseId,
    required String reason,
  }) async {
    await Future<void>.delayed(latency);
    final found = _cases
        .where((c) => c.paymentCase.id == caseId)
        .firstOrNull;
    if (found == null) throw const CaseNotFoundException();
    if (found.paymentCase.type == CaseType.disputed) {
      throw const DuplicateDisputeException();
    }
    return _summaryOf(found);
  }

  @override
  Future<RefundResult> refund({
    required String paymentId,
    required String reason,
    required String idempotencyKey,
  }) async {
    await Future<void>.delayed(latency);
    if (failNextRefund) {
      failNextRefund = false;
      throw const DuplicateRefundException();
    }
    final found = _cases
        .where((c) => c.payment.paymentId == paymentId)
        .firstOrNull;
    if (found == null) throw const CaseNotFoundException();
    return RefundResult(
      paymentId: paymentId,
      status: 'reversed',
      refundReference: 'rfnd_$paymentId',
    );
  }

  static CaseSummary _summaryOf(CaseDetail d) => CaseSummary(
    caseId: d.paymentCase.id,
    paymentId: d.paymentCase.paymentId,
    type: d.paymentCase.type,
    status: d.paymentCase.status,
    openedAt: d.paymentCase.openedAt,
    updatedAt: d.paymentCase.updatedAt,
  );
}
