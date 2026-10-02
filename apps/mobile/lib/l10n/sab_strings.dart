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
  String get notCoveredTitle => _t('notCoveredTitle');
  String get notCoveredBody => _t('notCoveredBody');
  String get contactSupport => _t('contactSupport');
  String get queuedOffline => _t('queuedOffline');
  String get offlineNoPayment => _t('offlineNoPayment');
  String get providerPickerTitle => _t('providerPickerTitle');
  String get reauthTitle => _t('reauthTitle');
  String get reauthBody => _t('reauthBody');
  String get reauthAction => _t('reauthAction');
  String get amountConfirmedAtPayment => _t('amountConfirmedAtPayment');
  String get selectService => _t('selectService');
  String get sendFailed => _t('sendFailed');
  String get questionLabel => _t('questionLabel');

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
  String get offlineReceipts => _t('offlineReceipts');

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
    'notCoveredTitle': 'Not covered yet',
    'notCoveredBody': 'We don’t have that service yet. We’ve recorded your request and can connect you to support.',
    'contactSupport': 'Contact support',
    'queuedOffline':
        'Your request is queued and will send when you’re back online.',
    'offlineNoPayment': 'Payments can’t be authorised while you’re offline.',
    'providerPickerTitle': 'Which one do you mean?',
    'reauthTitle': 'Session expired',
    'reauthBody':
        'Sign in again to keep going. Your screen is right where you left it.',
    'reauthAction': 'Sign in again',
    'amountConfirmedAtPayment': 'Amount confirmed at payment',
    'selectService': 'Select',
    'sendFailed':
        'We couldn’t work that out. Check your connection and try again.',
    'questionLabel': 'Question',
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
    'receiptsEmptyBody': 'Receipts from your payments will appear here.',
    'offlineReceipts':
        'Showing your saved receipts. New ones arrive when you reconnect.',
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
    'getStartedLoading': 'Dey check your device…',
    'showPasskey': 'Use passkey',
    'emptyTitle': 'You never pay anything',
    'emptyBody': 'Tell Sabi wetin you need to pay to start.',
    'composerHint': 'Wetin you wan pay?',
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
    'fallbackNote':
        'Some words still dey English while we finish this language.',
  };
}

/// The active copy, rebuilt when the locale changes so a language switch
/// re-renders the app.
final sabStringsProvider = Provider<SabStrings>(
  (ref) => SabStrings.lookup(ref.watch(localeProvider)),
);
