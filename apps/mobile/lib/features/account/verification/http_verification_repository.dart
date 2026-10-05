import '../../../core/api_client.dart';
import '../../../core/api_exception.dart';
import 'verification_models.dart';
import 'verification_repository.dart';

/// Live identity verification against the gateway (FEAT-002; C-020–C-022).
///
/// The transport detail never reaches the controller: a rejected identifier and
/// an already-running check map to the domain exceptions the screen already
/// renders, and every other gateway error is a retryable server failure. The
/// identifier is posted once and never stored client-side; C-021 returns only
/// the record the contract defines.
class HttpVerificationRepository implements VerificationRepository {
  HttpVerificationRepository(this._api);

  final SabApiClient _api;

  @override
  Future<AccountVerification> status() async {
    try {
      final body = await _api.get('/account/verification');
      return AccountVerification.fromJson(body);
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<VerificationSubmission> submit({
    required VerificationMethod method,
    required String identifier,
  }) async {
    try {
      // C-020 accepts with 202; the client treats every 2xx as a body, so the
      // pending submission is read directly rather than polling for it.
      final body = await _api.post(
        '/identity/verifications',
        body: {'method': method.wire, 'identifier': identifier},
      );
      return VerificationSubmission.fromJson(body);
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      // C-020: 400 is a rejected identifier; 409 is a check already running.
      if (e.statusCode == 400) throw const InvalidIdentifierException();
      if (e.statusCode == 409) throw const VerificationInProgressException();
      throw ApiServerFailure(e.message);
    }
  }

  @override
  Future<VerificationRecord> check(String verificationId) async {
    try {
      final body = await _api.get('/identity/verifications/$verificationId');
      return VerificationRecord.fromJson(body);
    } on ApiUnauthenticated {
      rethrow;
    } on ApiUnreachable {
      rethrow;
    } on ApiException catch (e) {
      throw ApiServerFailure(e.message);
    }
  }
}
