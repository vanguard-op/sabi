import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/sab_strings.dart';

/// Copy for the payment surfaces (FEAT-005/006/007).
///
/// Kept with the feature rather than in the shared `SabStrings`, so the payment
/// task owns exactly its own strings while still reading the active locale from
/// the shared provider. Pidgin falls back per key to English, so a gap shows
/// English rather than a blank (branding.md, "Internationalization").
class PaymentStrings {
  const PaymentStrings(this._values, this._fallback);

  final Map<String, String> _values;
  final Map<String, String> _fallback;

  static const PaymentStrings english = PaymentStrings(_en, _en);
  static const PaymentStrings pidgin = PaymentStrings(_pcm, _en);

  static PaymentStrings lookup(AppLocale locale) =>
      locale == AppLocale.pidgin ? pidgin : english;

  String _t(String key) => _values[key] ?? _fallback[key] ?? key;

  // Shared
  String get confirmTitle => _t('confirmTitle');
  String get authorisePayment => _t('authorisePayment');
  String get changeAmount => _t('changeAmount');
  String get chargesAndTerms => _t('chargesAndTerms');
  String get authorising => _t('authorising');
  String get amount => _t('amount');
  String get payee => _t('payee');
  String get charges => _t('charges');
  String get reference => _t('reference');
  String get total => _t('total');
  String get forLabel => _t('forLabel');
  String get retry => _t('retry');
  String get cancel => _t('cancel');
  String get close => _t('close');
  String get continueLabel => _t('continueLabel');
  String get back => _t('back');
  String get loadError => _t('loadError');

  // Confirmation states
  String get thisPayment => _t('thisPayment');
  String get amountConfirmedAtPayment => _t('amountConfirmedAtPayment');
  String get secondConfirmationTitle => _t('secondConfirmationTitle');
  String get secondConfirmationBody => _t('secondConfirmationBody');
  String get confirmAndPay => _t('confirmAndPay');
  String get failureTitle => _t('failureTitle');
  String get reconcilingTitle => _t('reconcilingTitle');
  String get reconcilingBody => _t('reconcilingBody');
  String get heldForKycTitle => _t('heldForKycTitle');
  String get heldForKycBody => _t('heldForKycBody');
  String get verifyNow => _t('verifyNow');
  String get offlineNoAuthorisation => _t('offlineNoAuthorisation');
  String get sessionExpired => _t('sessionExpired');

  // Federal (FEAT-006)
  String get federalTitle => _t('federalTitle');
  String get federalReferenceNeeded => _t('federalReferenceNeeded');
  String get federalReferenceLabel => _t('federalReferenceLabel');
  String get federalReferenceHint => _t('federalReferenceHint');
  String get collectionChangedTitle => _t('collectionChangedTitle');
  String get collectionChangedBody => _t('collectionChangedBody');
  String get reResolve => _t('reResolve');
  String get awaitingReceiptTitle => _t('awaitingReceiptTitle');
  String get awaitingReceiptBody => _t('awaitingReceiptBody');
  String get officialReceipt => _t('officialReceipt');
  String get receiptNumber => _t('receiptNumber');
  String get receiptVerified => _t('receiptVerified');
  String get receiptUnverified => _t('receiptUnverified');
  String get reconcileTitle => _t('reconcileTitle');
  String get reconcileBody => _t('reconcileBody');
  String get openReconciliation => _t('openReconciliation');

  // Failed bill payment and its refund recovery (C-035 revision 1; FEAT-009)
  String get billTokenFailedTitle => _t('billTokenFailedTitle');
  String get startRefund => _t('startRefund');
  String get refundStarting => _t('refundStarting');
  String get refundStartedTitle => _t('refundStartedTitle');
  String get refundStartedBody => _t('refundStartedBody');

  // Bills (FEAT-007)
  String get billTitle => _t('billTitle');
  String get recipientLabel => _t('recipientLabel');
  String get recipientHint => _t('recipientHint');
  String get recipientNotFound => _t('recipientNotFound');
  String get billerOfflineTitle => _t('billerOfflineTitle');
  String get billerOfflineBody => _t('billerOfflineBody');
  String get awaitingTokenTitle => _t('awaitingTokenTitle');
  String get awaitingTokenBody => _t('awaitingTokenBody');
  String get tokenLabel => _t('tokenLabel');
  String get tokenCopied => _t('tokenCopied');
  String get copyToken => _t('copyToken');
  String get tokenStored => _t('tokenStored');

  // Outcomes
  String get successTitle => _t('successTitle');
  String get successBody => _t('successBody');
  String get viewReceipt => _t('viewReceipt');
  String get doneLabel => _t('doneLabel');

  static const Map<String, String> _en = {
    'confirmTitle': 'Confirm payment',
    'authorisePayment': 'Authorise payment',
    'changeAmount': 'Change amount',
    'chargesAndTerms': 'Charges and terms',
    'authorising': 'Authorising payment…',
    'amount': 'Amount',
    'payee': 'Payee',
    'charges': 'Charges',
    'reference': 'Reference',
    'total': 'Total',
    'forLabel': 'For',
    'retry': 'Try again',
    'cancel': 'Cancel',
    'close': 'Close',
    'continueLabel': 'Continue',
    'back': 'Back',
    'loadError': 'We couldn’t load this payment. Try again.',
    'thisPayment': 'you’re paying',
    'amountConfirmedAtPayment': 'Amount confirmed at payment',
    'secondConfirmationTitle': 'Confirm this amount again',
    'secondConfirmationBody': 'This is above your usual limit. Authorise it once more and we’ll proceed.',
    'confirmAndPay': 'Yes, authorise',
    'failureTitle': 'Payment didn’t go through',
    'reconcilingTitle': 'Checking with the rail',
    'reconcilingBody': 'We don’t have a confirmed result yet. Nothing will be retried until we reconcile it.',
    'heldForKycTitle': 'Identity check needed',
    'heldForKycBody': 'This payment needs your identity verified. It is held, not failed. Verify to continue.',
    'verifyNow': 'Verify identity',
    'offlineNoAuthorisation':
        'You’re offline. A payment can’t be authorised until you reconnect.',
    'sessionExpired': 'Your session expired. Sign in again to continue.',
    'federalTitle': 'Federal payment',
    'federalReferenceNeeded': 'This payment needs a payer reference',
    'federalReferenceLabel': 'Payer reference',
    'federalReferenceHint': 'e.g. your TIN or assessment number',
    'collectionChangedTitle': 'Collection account changed',
    'collectionChangedBody': 'The agency has moved its collection account. Re-resolve the obligation so we pay the current one.',
    'reResolve': 'Re-resolve obligation',
    'awaitingReceiptTitle': 'Waiting for the official receipt',
    'awaitingReceiptBody': 'Your payment settled. The treasury e-receipt hasn’t arrived yet; we’ll keep checking.',
    'officialReceipt': 'Official e-receipt',
    'receiptNumber': 'Receipt number',
    'receiptVerified': 'Verified against the source',
    'receiptUnverified': 'Not verified against the source',
    'reconcileTitle': 'Payment not reflected at the agency',
    'reconcileBody': 'The rail confirmed but the agency record doesn’t show it yet. Open a reconciliation with your reference.',
    'openReconciliation': 'Open a reconciliation',
    'billTokenFailedTitle': 'No token was issued',
    'startRefund': 'Start a refund',
    'refundStarting': 'Starting your refund…',
    'refundStartedTitle': 'Refund started',
    'refundStartedBody': 'We’ve asked the rail to reverse this payment. We’ll update you on your preferred channel.',
    'billTitle': 'Pay this bill',
    'recipientLabel': 'Meter or phone number',
    'recipientHint': 'Enter the number you’re paying',
    'recipientNotFound': 'That number wasn’t found. Check it and try again.',
    'billerOfflineTitle': 'Biller is offline',
    'billerOfflineBody': 'We can’t reach this biller right now, so no payment is made. Try again later.',
    'awaitingTokenTitle': 'Waiting for your token',
    'awaitingTokenBody': 'Your payment settled. The token is still coming; we’ll keep checking and store it with your receipt.',
    'tokenLabel': 'Token',
    'tokenCopied': 'Token copied',
    'copyToken': 'Copy token',
    'tokenStored': 'Token saved with your receipt',
    'successTitle': 'Payment settled',
    'successBody': 'We stored your receipt. You can open it any time.',
    'viewReceipt': 'View receipt',
    'doneLabel': 'Done',
  };

  // Pidgin is intentionally partial; untranslated keys fall back to English.
  static const Map<String, String> _pcm = {
    'confirmTitle': 'Confirm payment',
    'authorisePayment': 'Authorise am',
    'changeAmount': 'Change the amount',
    'chargesAndTerms': 'Charges and terms',
    'authorising': 'Dey authorise…',
    'amount': 'Amount',
    'payee': 'Who you dey pay',
    'charges': 'Charges',
    'reference': 'Reference',
    'total': 'Total',
    'retry': 'Try again',
    'cancel': 'Cancel',
    'close': 'Close',
    'confirmAndPay': 'Yes, authorise am',
    'failureTitle': 'Payment no go through',
    'reconcilingTitle': 'We dey check with the rail',
    'heldForKycTitle': 'Identity check needed',
    'verifyNow': 'Verify identity',
    'billerOfflineTitle': 'Biller offline',
    'billerOfflineBody':
        'We no reach this biller now. No payment go happen. Try later.',
    'successTitle': 'Payment don settle',
    'doneLabel': 'Done',
  };
}

/// The active payment copy, rebuilt when the locale changes.
final paymentStringsProvider = Provider<PaymentStrings>(
  (ref) => PaymentStrings.lookup(ref.watch(localeProvider)),
);
