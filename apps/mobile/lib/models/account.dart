import 'package:flutter/foundation.dart';

import 'channel_link.dart';

/// Verification / KYC state shown on Account and gating regulated payments
/// (CONTRACTS.md C-008 `kycStatus`; FEAT-002).
enum VerificationStatus {
  unverified,
  pending,
  verified,
  suspended;

  static VerificationStatus parse(String raw) => switch (raw) {
    'pending' => VerificationStatus.pending,
    'verified' => VerificationStatus.verified,
    'suspended' => VerificationStatus.suspended,
    _ => VerificationStatus.unverified,
  };
}

/// The account record (CONTRACTS.md C-008).
@immutable
class Account {
  const Account({
    required this.id,
    this.displayName,
    required this.locale,
    required this.preferredChannel,
    required this.kycStatus,
    required this.accountStatus,
    this.channelLinks = const [],
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String? displayName;
  final String locale;
  final String preferredChannel;
  final VerificationStatus kycStatus;

  /// `active`, `suspended`, etc.
  final String accountStatus;
  final List<ChannelLink> channelLinks;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  bool get isSuspended => accountStatus == 'suspended';

  factory Account.fromJson(Map<String, dynamic> json) {
    final links = (json['channelLinks'] as List?) ?? const [];
    return Account(
      id: json['id'].toString(),
      displayName: json['displayName']?.toString(),
      locale: (json['locale'] ?? 'en').toString(),
      preferredChannel: (json['preferredChannel'] ?? 'app').toString(),
      kycStatus: VerificationStatus.parse((json['kycStatus'] ?? '').toString()),
      accountStatus: (json['accountStatus'] ?? 'active').toString(),
      channelLinks: links
          .whereType<Map>()
          .map((e) => ChannelLink.fromJson(e.cast<String, dynamic>()))
          .toList(growable: false),
      createdAt: DateTime.tryParse(json['createdAt']?.toString() ?? ''),
      updatedAt: DateTime.tryParse(json['updatedAt']?.toString() ?? ''),
    );
  }
}
