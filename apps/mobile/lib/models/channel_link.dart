import 'package:flutter/foundation.dart';

/// A linked channel address (CONTRACTS.md C-007). The link attaches to the same
/// account; a channel link never creates a second account.
@immutable
class ChannelLink {
  const ChannelLink({
    required this.id,
    required this.channel,
    required this.address,
    this.verifiedAt,
  });

  final String id;

  /// `ussd`, `sms`, or `whatsapp`.
  final String channel;
  final String address;
  final DateTime? verifiedAt;

  bool get isVerified => verifiedAt != null;

  factory ChannelLink.fromJson(Map<String, dynamic> json) => ChannelLink(
    id: json['id'].toString(),
    channel: json['channel'].toString(),
    address: json['address'].toString(),
    verifiedAt: DateTime.tryParse(json['verifiedAt']?.toString() ?? ''),
  );
}
