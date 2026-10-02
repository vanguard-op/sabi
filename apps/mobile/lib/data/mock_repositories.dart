import '../l10n/sab_strings.dart';
import '../models/account.dart';
import '../models/channel_link.dart';
import '../models/intent_result.dart';
import '../models/payment_method.dart';
import '../models/receipt_summary.dart';
import '../models/service_summary.dart';
import 'repositories.dart';

/// Thrown when a credential or recovery code is not accepted.
class InvalidCredentialException implements Exception {
  const InvalidCredentialException();
}

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
