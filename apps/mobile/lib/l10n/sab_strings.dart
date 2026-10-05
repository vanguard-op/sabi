import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Launch locales (branding.md, "Internationalization & Localization"):
/// Nigerian English and Nigerian Pidgin. Pidgin falls back to English per string
/// until a translation lands, and the app shows a short note when it does.
enum AppLocale {
  english('en', 'English', 'English'),
  pidgin('pcm', 'Pidgin', 'Naija');

  const AppLocale(this.code, this.englishLabel, this.nativeLabel);

  final String code;
  final String englishLabel;
  final String nativeLabel;

  static AppLocale parse(String? code) =>
      code == 'pcm' ? AppLocale.pidgin : AppLocale.english;
}

/// The active response language. Changing it re-renders the app (Account).
class LocaleController extends Notifier<AppLocale> {
  @override
  AppLocale build() => AppLocale.english;

  void set(AppLocale locale) => state = locale;
}

final localeProvider = NotifierProvider<LocaleController, AppLocale>(
  LocaleController.new,
);

/// All user-facing copy, externalized and looked up by locale. Pidgin values
/// fall back to English per key so a gap shows English rather than a blank.
class SabStrings {
  const SabStrings(this._values, this._fallback);

  final Map<String, String> _values;
  final Map<String, String> _fallback;

  static const SabStrings english = SabStrings(_en, _en);
  static const SabStrings pidgin = SabStrings(_pcm, _en);

  static SabStrings lookup(AppLocale locale) =>
      locale == AppLocale.pidgin ? pidgin : english;

  /// True when the active locale is missing any string and is showing English
  /// for it. Account surfaces this as a short note.
  bool get hasFallback =>
      _values != _fallback &&
      _fallback.keys.any((k) => !_values.containsKey(k));

  String _t(String key) => _values[key] ?? _fallback[key] ?? key;

  /// Fills `{name}` placeholders in a string with [values]. Used for copy that
  /// names the user's query or a date, so the sentence stays translatable.
  static String fill(String template, Map<String, String> values) {
    var out = template;
    for (final entry in values.entries) {
      out = out.replaceAll('{${entry.key}}', entry.value);
    }
    return out;
  }

  String get appName => _t('appName');
  String get tagline => _t('tagline');
  String get retry => _t('retry');
  String get cancel => _t('cancel');
  String get close => _t('close');
  String get continueLabel => _t('continueLabel');
  String get loading => _t('loading');

  // Welcome
  String get welcomeValue => _t('welcomeValue');
  String get getStarted => _t('getStarted');
  String get signIn => _t('signIn');
  String get dataHandling => _t('dataHandling');
  String get dataHandlingBody => _t('dataHandlingBody');
  String get checkingDevice => _t('checkingDevice');
  String get creatingAccount => _t('creatingAccount');
  String get passkeyUnsupportedTitle => _t('passkeyUnsupportedTitle');
  String get passkeyUnsupportedBody => _t('passkeyUnsupportedBody');
  String get passkeySetupUnavailableTitle => _t('passkeySetupUnavailableTitle');
  String get passkeySetupUnavailableBody => _t('passkeySetupUnavailableBody');
  String get passkeySetupUnavailableSignIn =>
      _t('passkeySetupUnavailableSignIn');
  String get passkeyRetry => _t('passkeyRetry');
  String get useRecoveryInstead => _t('useRecoveryInstead');
  String get offlineQueue => _t('offlineQueue');
  String get errorTitle => _t('errorTitle');
  String get errorGeneric => _t('errorGeneric');
  String get createFailed => _t('createFailed');
  String get recoveryTitle => _t('recoveryTitle');
  String get recoveryBody => _t('recoveryBody');
  String get recoveryCopy => _t('recoveryCopy');
  String get recoveryCopied => _t('recoveryCopied');
  String get recoveryAcknowledge => _t('recoveryAcknowledge');
  String get recoveryWarning => _t('recoveryWarning');

  // Sign in
  String get signInHeading => _t('signInHeading');
  String get continueWithPasskey => _t('continueWithPasskey');
  String get useRecoveryCode => _t('useRecoveryCode');
  String get recoveryCodeLabel => _t('recoveryCodeLabel');
  String get recoveryCodeHint => _t('recoveryCodeHint');
  String get submitRecovery => _t('submitRecovery');
  String get createAccount => _t('createAccount');
  String get verifying => _t('verifying');
  String get signInFailed => _t('signInFailed');
  String get passkeyFailed => _t('passkeyFailed');
  String get passkeyPrompt => _t('passkeyPrompt');
  String get unrecoverable => _t('unrecoverable');
  String get enrolPasskeyTitle => _t('enrolPasskeyTitle');
  String get enrolPasskeyBody => _t('enrolPasskeyBody');
  String get enrolPasskeyAction => _t('enrolPasskeyAction');
  String get later => _t('later');

  // Home
  String get homeTitle => _t('homeTitle');
  String get accountTooltip => _t('accountTooltip');
  String get composerHint => _t('composerHint');
  String get send => _t('send');
  String get emptyTitle => _t('emptyTitle');
  String get emptyBody => _t('emptyBody');
  String get somethingWrong => _t('somethingWrong');
  String get homeLoadError => _t('homeLoadError');
  String get composing => _t('composing');
  String get recent => _t('recent');
  String get clarifyingTitle => _t('clarifyingTitle');
  String get candidates => _t('candidates');
  String get conversationalReply => _t('conversationalReply');
  String get notCoveredTitle => _t('notCoveredTitle');
  String get unresolvedReply => _t('unresolvedReply');
  String get notCoveredBody => _t('notCoveredBody');
  String get contactSupport => _t('contactSupport');
  String get queuedOffline => _t('queuedOffline');
  String get offlineNoPayment => _t('offlineNoPayment');
  String get reauthTitle => _t('reauthTitle');
  String get reauthBody => _t('reauthBody');
  String get reauthAction => _t('reauthAction');
  String get amountConfirmedAtPayment => _t('amountConfirmedAtPayment');
  String get selectService => _t('selectService');
  String get sendFailed => _t('sendFailed');
  String get questionLabel => _t('questionLabel');

  // Home inline tasks (FEAT-011, C-012 revision 2). A task the conversation
  // resolves renders inline and completes there; the remaining screens are
  // reached where a non-conversation surface still leads to them.
  String get verifyInlineTitle => _t('verifyInlineTitle');
  String get verifyInlineBody => _t('verifyInlineBody');
  String get openVerificationScreen => _t('openVerificationScreen');
  String get recoveringTitle => _t('recoveringTitle');
  String get recoveringBody => _t('recoveringBody');
  String get openCase => _t('openCase');
  String get recordTitle => _t('recordTitle');
  String get recordCandidatesTitle => _t('recordCandidatesTitle');
  String get openReceipt => _t('openReceipt');
  String get noRecordTitle => _t('noRecordTitle');
  String get noRecordBody => _t('noRecordBody');

  // Status
  String get statusPending => _t('statusPending');
  String get statusSettled => _t('statusSettled');
  String get statusFailed => _t('statusFailed');
  String get statusAwaitingReceipt => _t('statusAwaitingReceipt');
  String get statusUnverified => _t('statusUnverified');
  String get statusVerified => _t('statusVerified');
  String get statusSuspended => _t('statusSuspended');

  // Account
  String get accountTitle => _t('accountTitle');
  String get profileGroup => _t('profileGroup');
  String get displayName => _t('displayName');
  String get displayNameUnset => _t('displayNameUnset');
  String get accountStatusLabel => _t('accountStatusLabel');
  String get accountStatusActive => _t('accountStatusActive');
  String get localeLabel => _t('localeLabel');
  String get verificationGroup => _t('verificationGroup');
  String get verificationUnverified => _t('verificationUnverified');
  String get verifyIdentity => _t('verifyIdentity');
  String get verificationPending => _t('verificationPending');
  String get verificationVerified => _t('verificationVerified');
  String get suspendedReason => _t('suspendedReason');
  String get channelsGroup => _t('channelsGroup');
  String get channelUssd => _t('channelUssd');
  String get channelSms => _t('channelSms');
  String get channelWhatsapp => _t('channelWhatsapp');
  String get channelNotLinked => _t('channelNotLinked');
  String get channelLinked => _t('channelLinked');
  String get channelPending => _t('channelPending');
  String get linkChannelTitle => _t('linkChannelTitle');
  String get linkChannel => _t('linkChannel');
  String get channelAddressLabel => _t('channelAddressLabel');
  String get channelAlreadyLinked => _t('channelAlreadyLinked');
  String get channelLinkFailed => _t('channelLinkFailed');
  String get methodsGroup => _t('methodsGroup');
  String get methodSaved => _t('methodSaved');
  String get noMethods => _t('noMethods');
  String get signOut => _t('signOut');
  String get loadError => _t('loadError');
  String get offlineAccount => _t('offlineAccount');
  String get fallbackNote => _t('fallbackNote');

  // Receipts
  String get receiptsTitle => _t('receiptsTitle');
  String get receiptsEmptyTitle => _t('receiptsEmptyTitle');
  String get receiptsEmptyBody => _t('receiptsEmptyBody');
  String get receiptsEmptyAction => _t('receiptsEmptyAction');
  String get offlineReceipts => _t('offlineReceipts');
  String get searchReceiptsHint => _t('searchReceiptsHint');
  String get searchReceiptsLabel => _t('searchReceiptsLabel');
  String get noResultsTitle => _t('noResultsTitle');
  String get noResultsBody => _t('noResultsBody');
  String get clearSearch => _t('clearSearch');
  String get storageWarning => _t('storageWarning');
  String get loadMore => _t('loadMore');

  // Receipt detail
  String get receiptDetailTitle => _t('receiptDetailTitle');
  String get receiptPayeeLabel => _t('receiptPayeeLabel');
  String get receiptAmountLabel => _t('receiptAmountLabel');
  String get receiptReferenceLabel => _t('receiptReferenceLabel');
  String get receiptDateLabel => _t('receiptDateLabel');
  String get receiptOfficialIdLabel => _t('receiptOfficialIdLabel');
  String get receiptVerifiedLine => _t('receiptVerifiedLine');
  String get receiptUnverifiedLine => _t('receiptUnverifiedLine');
  String get receiptAwaitingLine => _t('receiptAwaitingLine');
  String get receiptStatusLabel => _t('receiptStatusLabel');
  String get shareReceipt => _t('shareReceipt');
  String get exportReceipt => _t('exportReceipt');
  String get raiseDispute => _t('raiseDispute');
  String get receiptNotFound => _t('receiptNotFound');
  String get receiptShareReady => _t('receiptShareReady');
  String get receiptExportReady => _t('receiptExportReady');
  String get receiptDocumentPending => _t('receiptDocumentPending');
  String get receiptDocumentFailed => _t('receiptDocumentFailed');
  String get kindOfficialReceipt => _t('kindOfficialReceipt');
  String get kindBillerConfirmation => _t('kindBillerConfirmation');
  String get kindToken => _t('kindToken');

  // Case
  String get caseTitle => _t('caseTitle');
  String get caseStatePending => _t('caseStatePending');
  String get caseStateReconciling => _t('caseStateReconciling');
  String get caseStateRefundInitiated => _t('caseStateRefundInitiated');
  String get caseStartRefund => _t('caseStartRefund');
  String get caseStateAwaitingBiller => _t('caseStateAwaitingBiller');
  String get caseStateEscalated => _t('caseStateEscalated');
  String get caseStateResolved => _t('caseStateResolved');
  String get caseLastUpdate => _t('caseLastUpdate');
  String get caseExpectedWindow => _t('caseExpectedWindow');
  String get caseExpectedWindowValue => _t('caseExpectedWindowValue');
  String get caseTimelineTitle => _t('caseTimelineTitle');
  String get caseContactSupport => _t('caseContactSupport');
  String get caseViewReceipt => _t('caseViewReceipt');
  String get caseNotFound => _t('caseNotFound');
  String get caseOffline => _t('caseOffline');
  String get caseRefundBlocked => _t('caseRefundBlocked');
  String get caseRefundSubmitted => _t('caseRefundSubmitted');
  String get caseDisputeBlocked => _t('caseDisputeBlocked');
  String get caseDisputeSubmitted => _t('caseDisputeSubmitted');
  String get caseSupportBody => _t('caseSupportBody');
  String get caseReferenceLabel => _t('caseReferenceLabel');
  String get caseTypeFailedNoDelivery => _t('caseTypeFailedNoDelivery');
  String get caseTypeDisputed => _t('caseTypeDisputed');
  String get caseTypeRefund => _t('caseTypeRefund');
  String get caseTypeReceiptMissing => _t('caseTypeReceiptMissing');
  String get caseOpenedLabel => _t('caseOpenedLabel');
  String get caseActorSystem => _t('caseActorSystem');
  String get caseActorUser => _t('caseActorUser');
  String get caseActorRail => _t('caseActorRail');
  String get caseActorProvider => _t('caseActorProvider');

  // Confirmation summary / amount entry / fallback
  String get confirmTitle => _t('confirmTitle');
  String get amount => _t('amount');
  String get payee => _t('payee');
  String get charges => _t('charges');
  String get reference => _t('reference');
  String get amountEntryTitle => _t('amountEntryTitle');
  String get amountEntryHint => _t('amountEntryHint');
  String get amountOutOfRange => _t('amountOutOfRange');
  String get requiredField => _t('requiredField');
  String get unknownComponent => _t('unknownComponent');
  String get validationRequired => _t('validationRequired');

  // Gated features
  String get notYetTitle => _t('notYetTitle');
  String get notYetBody => _t('notYetBody');
  String get back => _t('back');

  static const Map<String, String> _en = {
    'appName': 'Sabi',
    'tagline': 'Say it. Pay it. Prove it.',
    'retry': 'Try again',
    'cancel': 'Cancel',
    'close': 'Close',
    'continueLabel': 'Continue',
    'loading': 'Loading',
    'welcomeValue': 'Pay government obligations and everyday bills by telling Sabi what you need.',
    'getStarted': 'Get started',
    'signIn': 'Sign in',
    'dataHandling': 'How Sabi handles your data',
    'dataHandlingBody': 'Sabi uses your account only to resolve and pay what you ask for. It never sells your data, and no payment is made without your confirmation.',
    'checkingDevice': 'Checking this device…',
    'creatingAccount': 'Creating your account…',
    'passkeyUnsupportedTitle': 'This device can’t use a passkey',
    'passkeyUnsupportedBody': 'You can still create an account with a recovery code and email. That is less secure than a passkey, so save the code carefully.',
    'passkeySetupUnavailableTitle': 'Passkey setup isn’t available here',
    'passkeySetupUnavailableBody': 'This build can’t set up a passkey on this device yet, so passkeys won’t work right now. You can create an account with a recovery code instead. Nothing you entered was rejected.',
    'passkeySetupUnavailableSignIn': 'Passkeys aren’t available on this build. Sign in with a recovery code instead.',
    'passkeyRetry': 'The passkey prompt didn’t finish. Give it another try.',
    'useRecoveryInstead': 'Create account with a recovery code',
    'offlineQueue': 'You’re offline. Account creation is queued and will finish when you reconnect.',
    'errorTitle': 'Something went wrong',
    'errorGeneric':
        'We couldn’t finish that. Check your connection and try again.',
    'createFailed': 'We couldn’t create your account. Nothing was saved.',
    'recoveryTitle': 'Save your recovery code',
    'recoveryBody': 'This code is shown once. If you lose your passkey, it is the only way back into your account.',
    'recoveryCopy': 'Copy code',
    'recoveryCopied': 'Recovery code copied',
    'recoveryAcknowledge': 'I’ve saved my recovery code',
    'recoveryWarning': 'Without this code, and without your passkey, the account cannot be recovered.',
    'signInHeading': 'Welcome back',
    'continueWithPasskey': 'Continue with passkey',
    'useRecoveryCode': 'Use a recovery code',
    'recoveryCodeLabel': 'Recovery code',
    'recoveryCodeHint': 'Paste the code you saved',
    'submitRecovery': 'Sign in with code',
    'createAccount': 'Create an account',
    'verifying': 'Checking…',
    'signInFailed': 'That didn’t match. Check the code and try again.',
    'passkeyFailed':
        'The passkey wasn’t accepted. Try again or use a recovery code.',
    'passkeyPrompt': 'Follow the prompt on your device…',
    'unrecoverable': 'If you’ve lost your passkey and your recovery code, this account can’t be recovered.',
    'enrolPasskeyTitle': 'Add a passkey to this device',
    'enrolPasskeyBody': 'You signed in with a recovery code. Add a passkey so next time is one tap.',
    'enrolPasskeyAction': 'Add passkey',
    'later': 'Not now',
    'homeTitle': 'Home',
    'accountTooltip': 'Account',
    'composerHint': 'What do you need to pay?',
    'send': 'Send',
    'emptyTitle': 'No payments yet',
    'emptyBody': 'Tell Sabi what you need to pay to get started.',
    'somethingWrong': 'Something went wrong',
    'homeLoadError': 'We couldn’t load your activity.',
    'composing': 'Working on it…',
    'recent': 'Recent',
    'clarifyingTitle': 'Just to confirm',
    'candidates': 'Closest matches',
    'conversationalReply': 'I can pay government obligations and everyday bills for you — levies, taxes, airtime, data, a utility, or a biller. Tell me what you need to pay in your own words, English or Pidgin, and I’ll take it from there.',
    'notCoveredTitle': 'No resolution yet',
    'unresolvedReply':
        'Three answers in and I still can’t tell which service you mean, so I haven’t started anything with your money. You can search the catalogue yourself, or ask support to take it from here. If you know the collecting body’s name, or the reference you’re paying, tell me and I’ll pick it up.',
    'notCoveredBody':
        'There’s no resolution for that service right now, so I haven’t started anything. Tell me the collecting body’s name, the agency, or the reference you’re paying, and I’ll look again. You can also search the catalogue yourself or reach support.',
    'contactSupport': 'Contact support',
    'queuedOffline':
        'Your request is queued and will send when you’re back online.',
    'offlineNoPayment': 'Payments can’t be authorised while you’re offline.',
    'reauthTitle': 'Session expired',
    'reauthBody':
        'Sign in again to keep going. Your screen is right where you left it.',
    'reauthAction': 'Sign in again',
    'amountConfirmedAtPayment': 'Amount confirmed at payment',
    'selectService': 'Select',
    'sendFailed':
        'We couldn’t work that out. Check your connection and try again.',
    'questionLabel': 'Question',
    'verifyInlineTitle': 'Verify your identity',
    'verifyInlineBody': 'This payment needs your identity verified. It is held, not failed. Verify to continue, or open the identity screen.',
    'openVerificationScreen': 'Open identity screen',
    'recoveringTitle': 'This payment needs attention',
    'recoveringBody': 'The payment didn’t complete as expected. We can show you the state and the next step here, or open the case for the full timeline.',
    'openCase': 'Open case',
    'recordTitle': 'Your record',
    'recordCandidatesTitle': 'Which record?',
    'openReceipt': 'Open in Receipts',
    'noRecordTitle': 'No record found',
    'noRecordBody':
        'There’s no record matching that yet, so nothing has changed. Check the reference, the payee, or the date and tell me, and I’ll look again. You can also search your receipts yourself.',
    'statusPending': 'Pending',
    'statusSettled': 'Settled',
    'statusFailed': 'Failed',
    'statusAwaitingReceipt': 'Awaiting receipt',
    'statusUnverified': 'Not verified',
    'statusVerified': 'Verified',
    'statusSuspended': 'Suspended',
    'accountTitle': 'Account',
    'profileGroup': 'Profile',
    'displayName': 'Name',
    'displayNameUnset': 'Not set',
    'accountStatusLabel': 'Account status',
    'accountStatusActive': 'Active',
    'localeLabel': 'Language',
    'verificationGroup': 'Identity',
    'verificationUnverified':
        'Verify your identity to make regulated payments.',
    'verifyIdentity': 'Verify identity',
    'verificationPending': 'Your verification is being checked.',
    'verificationVerified': 'Your identity is verified.',
    'suspendedReason':
        'This account is suspended. Payments are disabled. Contact support.',
    'channelsGroup': 'Linked channels',
    'channelUssd': 'USSD number',
    'channelSms': 'SMS number',
    'channelWhatsapp': 'WhatsApp number',
    'channelNotLinked': 'Not linked',
    'channelLinked': 'Linked',
    'channelPending': 'Pending',
    'linkChannelTitle': 'Link a channel',
    'linkChannel': 'Link',
    'channelAddressLabel': 'Number',
    'channelAlreadyLinked': 'That number is already linked to another account. We’ve let the owner know.',
    'channelLinkFailed': 'We couldn’t link that number.',
    'methodsGroup': 'Payment methods',
    'methodSaved': 'Saved method',
    'noMethods': 'No payment methods yet',
    'signOut': 'Sign out',
    'loadError': 'We couldn’t load your account.',
    'offlineAccount': 'Showing your last known account details.',
    'fallbackNote':
        'Some text is shown in English while we finish this language.',
    'receiptsTitle': 'Receipts',
    'receiptsEmptyTitle': 'No receipts yet',
    'receiptsEmptyBody': 'Receipts from your payments will appear here. Make a payment to keep the first one.',
    'receiptsEmptyAction': 'Make a payment',
    'offlineReceipts':
        'Showing your saved receipts. New ones arrive when you reconnect.',
    'searchReceiptsHint': 'Search by reference, agency, or date',
    'searchReceiptsLabel': 'Search receipts',
    'noResultsTitle': 'No matches',
    'noResultsBody':
        'Nothing matched “{query}”. Try a reference, an agency, or a date.',
    'clearSearch': 'Clear search',
    'storageWarning': 'We couldn’t save this receipt yet. Keep the transaction reference until it appears.',
    'loadMore': 'Load more',
    'receiptDetailTitle': 'Receipt',
    'receiptPayeeLabel': 'Payee',
    'receiptAmountLabel': 'Amount',
    'receiptReferenceLabel': 'Reference',
    'receiptDateLabel': 'Date',
    'receiptOfficialIdLabel': 'Official receipt number',
    'receiptVerifiedLine': 'Checked and confirmed against the source.',
    'receiptUnverifiedLine': 'We couldn’t confirm this against the source.',
    'receiptAwaitingLine': 'We’re still checking this with the source.',
    'receiptStatusLabel': 'Receipt status',
    'shareReceipt': 'Share receipt',
    'exportReceipt': 'Export as document',
    'raiseDispute': 'Raise a dispute',
    'receiptNotFound': 'This receipt couldn’t be found.',
    'receiptShareReady': 'Receipt is ready to share.',
    'receiptExportReady': 'Receipt document is ready.',
    'receiptDocumentPending':
        'The official document isn’t ready yet. Try again shortly.',
    'receiptDocumentFailed': 'We couldn’t prepare the document.',
    'kindOfficialReceipt': 'Official receipt',
    'kindBillerConfirmation': 'Biller confirmation',
    'kindToken': 'Token',
    'caseTitle': 'Case',
    'caseStatePending': 'Pending',
    'caseStateReconciling': 'Reconciling',
    'caseStateRefundInitiated': 'Refund started',
    'caseStartRefund': 'Start a refund',
    'caseStateAwaitingBiller': 'Waiting on the biller',
    'caseStateEscalated': 'Escalated',
    'caseStateResolved': 'Resolved',
    'caseLastUpdate': 'Last updated {date}',
    'caseExpectedWindow': 'Expected resolution',
    'caseExpectedWindowValue': 'Within 3 working days',
    'caseTimelineTitle': 'What’s happened',
    'caseContactSupport': 'Contact support',
    'caseViewReceipt': 'View the receipt',
    'caseNotFound': 'This case couldn’t be found.',
    'caseOffline': 'You’re offline. This is the last known state; we’ll update it when you reconnect.',
    'caseRefundBlocked': 'A refund for this reference is already in progress, so we didn’t send a second one.',
    'caseRefundSubmitted': 'Refund started. We’ll keep this case updated.',
    'caseDisputeBlocked': 'A dispute is already open on this payment, so we didn’t raise another one.',
    'caseDisputeSubmitted': 'Dispute raised. We’ll keep this case updated.',
    'caseSupportBody':
        'Quote your case reference so support can pick it up straight away.',
    'caseReferenceLabel': 'Case reference',
    'caseTypeFailedNoDelivery': 'Debited, not delivered',
    'caseTypeDisputed': 'Disputed',
    'caseTypeRefund': 'Refund',
    'caseTypeReceiptMissing': 'Receipt missing',
    'caseOpenedLabel': 'Opened {date}',
    'caseActorSystem': 'Sabi',
    'caseActorUser': 'You',
    'caseActorRail': 'Payment rail',
    'caseActorProvider': 'Provider',
    'confirmTitle': 'Confirm',
    'amount': 'Amount',
    'payee': 'Payee',
    'charges': 'Charges',
    'reference': 'Reference',
    'amountEntryTitle': 'Enter amount',
    'amountEntryHint': 'Amount in naira',
    'amountOutOfRange': 'Enter an amount within the allowed range.',
    'requiredField': 'This is needed',
    'unknownComponent':
        'The assistant sent a form we don’t recognise, so here’s a simple one.',
    'validationRequired': 'Check the highlighted fields and try again.',
    'notYetTitle': 'Coming soon',
    'notYetBody': 'This part of Sabi isn’t available yet.',
    'back': 'Back',
  };

  // Pidgin is intentionally partial at launch; untranslated keys fall back to
  // English and Account shows the fallback note.
  static const Map<String, String> _pcm = {
    'tagline': 'Talk am. Pay am. Show proof.',
    'welcomeValue': 'Pay government levy and everyday bills just by telling Sabi wetin you need.',
    'getStarted': 'Start now',
    'signIn': 'Sign in',
    'dataHandling': 'How Sabi dey handle your data',
    'passkeyUnsupportedTitle': 'This device no fit use passkey',
    'passkeyUnsupportedBody': 'You still fit create account with recovery code and email. That one no strong like passkey, so keep the code well.',
    'passkeySetupUnavailableTitle': 'Passkey setup no dey work here',
    'passkeySetupUnavailableBody': 'This build never set up passkey on this device yet, so passkey no go work right now. You fit create account with recovery code instead. Nothing you enter no dey rejected.',
    'passkeySetupUnavailableSignIn':
        'Passkey no dey this build. Use recovery code take sign in.',
    'passkeyRetry': 'The passkey prompt no finish. Try am again.',
    'getStartedLoading': 'Dey check your device…',
    'showPasskey': 'Use passkey',
    'emptyTitle': 'You never pay anything',
    'emptyBody': 'Tell Sabi wetin you need to pay to start.',
    'composerHint': 'Wetin you wan pay?',
    'conversationalReply': 'I fit pay government levy and everyday bills for you. Tell me wetin you wan pay, I go handle am.',
    'send': 'Send',
    'retry': 'Try again',
    'signOut': 'Comot',
    'accountTitle': 'Account',
    'homeTitle': 'Home',
    'receiptsTitle': 'Receipts',
    'statusPending': 'Dey wait',
    'statusSettled': 'Don settle',
    'statusFailed': 'E fail',
    'statusUnverified': 'Never verify',
    'statusVerified': 'Don verify',
    'verificationUnverified': 'Verify your identity before you go pay.',
    'verifyIdentity': 'Verify identity',
    'linkChannel': 'Link',
    'channelNotLinked': 'Never link',
    'channelLinked': 'Don link',
    'receiptsEmptyAction': 'Make a payment',
    'searchReceiptsHint': 'Find by reference, agency, or date',
    'searchReceiptsLabel': 'Find receipt',
    'noResultsTitle': 'Nothing match',
    'clearSearch': 'Clear am',
    'loadMore': 'Load more',
    'shareReceipt': 'Share receipt',
    'exportReceipt': 'Export am',
    'caseStatePending': 'Dey wait',
    'caseStateReconciling': 'Dey check am',
    'caseStateRefundInitiated': 'Refund don start',
    'caseStateAwaitingBiller': 'Dey wait for biller',
    'caseStateEscalated': 'Don escalate',
    'caseStateResolved': 'Don resolve',
    'caseContactSupport': 'Contact support',
    'caseViewReceipt': 'See the receipt',
    'caseOffline': 'You no get network. This na the last state we sabi.',
    'verifyInlineTitle': 'Verify your identity',
    'verifyInlineBody': 'This payment need your identity verify first. E dey hold, e no fail. Verify to continue, or open the identity screen.',
    'openCase': 'Open case',
    'recordTitle': 'Your record',
    'openReceipt': 'Open for Receipts',
    'noRecordTitle': 'No record found',
    'noRecordBody':
        'No record match that one yet, so nothing don change. Check the reference, who you pay, or the date come tell me, I go look again. You fit also search your receipts yourself.',
    'fallbackNote':
        'Some words still dey English while we finish this language.',
  };
}

/// The active copy, rebuilt when the locale changes so a language switch
/// re-renders the app.
final sabStringsProvider = Provider<SabStrings>(
  (ref) => SabStrings.lookup(ref.watch(localeProvider)),
);
