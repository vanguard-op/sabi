import 'package:intl/intl.dart';

/// Money is stored as integer minor units (kobo) with an explicit currency
/// (DELIVERY.md conventions) and formatted for display only. Formatting uses
/// locale APIs, never a hardcoded pattern.
class SabMoney {
  const SabMoney._();

  static const String defaultCurrency = 'NGN';

  /// Display symbol for a currency code.
  static String symbolFor(String currency) => switch (currency) {
    'NGN' => '₦',
    _ => '$currency ',
  };

  static String format(
    int minorUnits, {
    String currency = defaultCurrency,
    String locale = 'en',
  }) {
    final value = minorUnits / 100;
    return NumberFormat.currency(
      locale: _intlLocale(locale),
      symbol: symbolFor(currency),
      decimalDigits: 2,
    ).format(value);
  }

  static String formatSigned(
    int minorUnits, {
    required bool negative,
    String currency = defaultCurrency,
    String locale = 'en',
  }) =>
      '${negative ? '-' : ''}${format(minorUnits, currency: currency, locale: locale)}';

  /// Formats an RFC 3339 UTC timestamp in the active locale.
  static String formatDate(DateTime value, {String locale = 'en'}) =>
      DateFormat.yMMMd(_intlLocale(locale)).format(value.toLocal());

  static String _intlLocale(String locale) => switch (locale) {
    'pcm' || 'en' => 'en_NG',
    _ => locale,
  };
}
