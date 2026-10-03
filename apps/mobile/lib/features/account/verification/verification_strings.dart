import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../l10n/sab_strings.dart';

/// Copy for the Identity Verification surface.
///
/// Every other screen reads from the central catalogue in `l10n/sab_strings.dart`;
/// this feature keeps its strings beside the screen while that catalogue is
/// outside the feature's write boundary. The same per-key English fallback is
/// honoured so a partial Pidgin translation never shows a blank.
class VerificationStrings {
  const VerificationStrings(this._values, this._fallback);

  final Map<String, String> _values;
  final Map<String, String> _fallback;

  static const VerificationStrings english = VerificationStrings(_en, _en);
  static const VerificationStrings pidgin = VerificationStrings(_pcm, _en);

  static VerificationStrings lookup(AppLocale locale) =>
      locale == AppLocale.pidgin ? pidgin : english;

  String _t(String key) => _values[key] ?? _fallback[key] ?? key;

  String get title => _t('title');
  String get heading => _t('heading');
  String get introUnverified => _t('introUnverified');
  String get introPending => _t('introPending');
  String get introVerified => _t('introVerified');
  String get introRejected => _t('introRejected');
  String get ninLabel => _t('ninLabel');
  String get ninHint => _t('ninHint');
  String get bvnLabel => _t('bvnLabel');
  String get bvnHint => _t('bvnHint');
  String get bvnNote => _t('bvnNote');
  String get verify => _t('verify');
  String get verifying => _t('verifying');
  String get dataUse => _t('dataUse');
  String get dataUseBody => _t('dataUseBody');
  String get requiredField => _t('requiredField');
  String get invalidNin => _t('invalidNin');
  String get invalidBvn => _t('invalidBvn');
  String get noMatchTitle => _t('noMatchTitle');
  String get noMatchBody => _t('noMatchBody');
  String get correctDetails => _t('correctDetails');
  String get contactSupport => _t('contactSupport');
  String get pendingTitle => _t('pendingTitle');
  String get pendingBody => _t('pendingBody');
  String get verifiedTitle => _t('verifiedTitle');
  String get verifiedBody => _t('verifiedBody');
  String get resumePayment => _t('resumePayment');
  String get backToAccount => _t('backToAccount');
  String get rejectedTitle => _t('rejectedTitle');
  String get rejectedBody => _t('rejectedBody');
  String get loadError => _t('loadError');
  String get submitError => _t('submitError');
  String get retry => _t('retry');
  String get offlineBody => _t('offlineBody');
  String get offlineAction => _t('offlineAction');
  String get heldPaymentNotice => _t('heldPaymentNotice');
  String get heldPaymentBody => _t('heldPaymentBody');
  String get statusUnverified => _t('statusUnverified');
  String get statusPending => _t('statusPending');
  String get statusVerified => _t('statusVerified');
  String get statusRejected => _t('statusRejected');

  static const Map<String, String> _en = {
    'title': 'Identity verification',
    'heading': 'Verify your identity',
    'introUnverified': 'Verify once so regulated payments can go through. Discovery stays open either way.',
    'introPending': 'Your details are with the national identity provider. This usually takes a moment.',
    'introVerified': 'Your identity is verified on this account.',
    'introRejected':
        'We could not verify this identity. Contact support to continue.',
    'ninLabel': 'National Identity Number (NIN)',
    'ninHint': '11 digits',
    'bvnLabel': 'Bank Verification Number (BVN)',
    'bvnHint': '11 digits',
    'bvnNote': 'This payment rail requires your BVN as well.',
    'verify': 'Verify identity',
    'verifying': 'Checking your details…',
    'dataUse': 'How we use your identity data',
    'dataUseBody': 'Your NIN and BVN are sent to the national identity provider only to confirm who you are. We keep the result on your account, not the numbers themselves, and we never sell them.',
    'requiredField': 'Enter this number to continue.',
    'invalidNin': 'A NIN is 11 digits. Check the number and try again.',
    'invalidBvn': 'A BVN is 11 digits. Check the number and try again.',
    'noMatchTitle': 'No match found',
    'noMatchBody': 'The details did not match the identity record. Check them and try once more.',
    'correctDetails': 'Correct my details',
    'contactSupport': 'Contact support',
    'pendingTitle': 'Verification pending',
    'pendingBody': 'The provider is unavailable right now, so your check is queued. We will update your account when it completes. You can keep using discovery.',
    'verifiedTitle': 'You are verified',
    'verifiedBody':
        'Regulated payments can now go through without asking again.',
    'resumePayment': 'Back to payment',
    'backToAccount': 'Back to account',
    'rejectedTitle': 'Verification rejected',
    'rejectedBody': 'Payments that need verification are paused on this account. Contact support with your reference so we can help.',
    'loadError': 'We couldn’t load your verification status.',
    'submitError': 'We couldn’t send your details just now. Nothing was saved — try again.',
    'retry': 'Try again',
    'offlineBody': 'You’re offline. Verification needs a connection to run.',
    'offlineAction': 'Verification resumes when you are back online.',
    'heldPaymentNotice': 'This payment is held',
    'heldPaymentBody': 'It needs verification before it can go through. The payment will resume once you are verified.',
    'statusUnverified': 'Not verified',
    'statusPending': 'Pending',
    'statusVerified': 'Verified',
    'statusRejected': 'Rejected',
  };

  // Pidgin is intentionally partial; untranslated keys fall back to English.
  static const Map<String, String> _pcm = {
    'title': 'Verify identity',
    'heading': 'Verify who you be',
    'verify': 'Verify identity',
    'verifying': 'We dey check your details…',
    'statusUnverified': 'Never verify',
    'statusPending': 'Dey wait',
    'statusVerified': 'Don verify',
    'statusRejected': 'Dem reject am',
    'requiredField': 'Put this number to continue.',
    'retry': 'Try again',
    'backToAccount': 'Go back to account',
  };
}

/// The active verification copy, rebuilt when the locale changes.
final verificationStringsProvider = Provider<VerificationStrings>(
  (ref) => VerificationStrings.lookup(ref.watch(localeProvider)),
);
