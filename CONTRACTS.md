# Sabi: contracts

One entry per interface. `Frozen` once agreed, `Implemented` once shipped and conformed. A change
after `Frozen` is a change request: mark it `Frozen (revision N)` and re-dispatch both sides.

### C-001: POST /v1/auth/register/options
Status: Implemented
Auth: None (public, unauthenticated)
Request: locale: string (en|pcm)
Response 200: challengeId: string, publicKey: object (WebAuthn PublicKeyCredentialCreationOptions)
Errors: 400 (invalid locale), 429 (rate limited)

### C-002: POST /v1/auth/register/verify
Status: Implemented
Auth: None (public, unauthenticated)
Request: challengeId: string, credential: object (WebAuthn attestation), displayName: string|null, locale: string (en|pcm)
Response 201: user: User, recoveryCode: string (shown once, single-use), session: HttpOnly Secure cookie
Errors: 400 (invalid attestation), 409 (credential already registered), 410 (challenge expired)

### C-003: POST /v1/auth/login/options
Status: Implemented
Auth: None (public, unauthenticated)
Request: —
Response 200: challengeId: string, publicKey: object (WebAuthn PublicKeyCredentialRequestOptions)
Errors: 429 (rate limited)

### C-004: POST /v1/auth/login/verify
Status: Implemented
Auth: None (public, unauthenticated)
Request: challengeId: string, credential: object (WebAuthn assertion)
Response 200: user: User, session: HttpOnly Secure cookie
Errors: 400 (invalid assertion), 401 (no matching credential), 410 (challenge expired)

### C-005: POST /v1/auth/recovery/verify
Status: Implemented
Auth: None (public, unauthenticated)
Request: recoveryCode: string
Response 200: user: User, mustEnrolPasskey: boolean (true), session: HttpOnly Secure cookie
Errors: 401 (invalid code), 409 (code already used)

### C-006: POST /v1/auth/recovery/regenerate
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: recoveryCode: string (shown once, single-use)
Errors: 401 (unauthenticated)

### C-007: POST /v1/auth/channel-links
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: channel: string (ussd|sms|whatsapp), address: string
Response 201: id: string, channel: string, address: string, verifiedAt: string|null
Errors: 409 (address already linked to another account; owner notified), 422 (invalid address)

### C-008: GET /v1/account/me
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: id: string, displayName: string|null, locale: string, preferredChannel: string, kycStatus: string, accountStatus: string, channelLinks: array of ChannelLink, createdAt: string, updatedAt: string
Errors: 401 (unauthenticated)

### C-009: POST /v1/agent/intents
Status: Frozen (revision 4)
Auth: Session cookie (authenticated account owner)
Request: text: string (non-empty, max 200 chars), locale: string (en|pcm), channel: string (app|ussd|sms|whatsapp), history: object[] (optional, oldest first, max 6, each {role: user|assistant, text: string})
Response 200: reply: string|null (the model-authored user-facing message in `locale`; null when none was produced), intent: object (intentType: string (gov_payment|bill_payment|discovery|status_check|receipt_lookup|non_command|unknown), target: string|null, amount: integer|null (minor units, kobo), currency: string, reference: string|null, constraints: object, confidence: number, detectedLanguage: string (en|pcm|ha|yo|ig|null)), candidates: ServiceSummary[], source: string (model|fallback)
Errors: 400 (empty or oversized text; malformed or oversized history), 429 (rate limited)

### C-010: GET /v1/catalogue/search
Status: Implemented (revision 2)
Auth: Session cookie (authenticated account owner)
Request: q: string (non-empty, max 200 chars), category: string|null, limit: integer (default 5, max 5)
Response 200: results: ServiceSummary[], noMatch: boolean
Errors: 400 (missing or over-length q), 429 (rate limited)
ServiceSummary: serviceId: string, name: string, collectingBody: string, category: string, knownAmount: integer|null (minor units, kobo), currency: string, status: string, confidence: number

### C-011: GET /v1/catalogue/services/{serviceId}
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: service: Service
Errors: 404 (unknown service)

### C-012: POST /v1/agent/surfaces
Status: Frozen (revision 2)
Auth: Session cookie (authenticated account owner)
Request: task: string (confirmation|amount_entry|receipt|discovery|verification|recovery), context: object (for `receipt`, may carry a resolved record reference from a record lookup instead of a post-payment service payment), catalogId: string (the client's published Sabi A2UI catalog, negotiated from supportedCatalogIds)
Response 200: messages: array of object (A2UI message stream conforming to the published catalog: createSurface | updateComponents | updateDataModel), fallback: string (task key)
Errors: 200 with fallback on invalid composition, unknown component, or no compatible catalog; 400 (unknown task), 429 (rate limited)

### C-013: POST /v1/providers
Status: Implemented
Auth: Operator session cookie + MFA, role provider review analyst
Request: name: string, type: string (agency|biller|merchant|aggregator), contactEmail: string
Response 201: provider: Provider (status pending)
Errors: 401 (unauthenticated), 403 (role or MFA missing), 409 (duplicate provider), 422 (invalid input)

### C-014: POST /v1/providers/{providerId}/capabilities
Status: Implemented
Auth: Operator session cookie + MFA, role provider review analyst
Request: name: string, serviceId: string|null, inputSchemaRef: string, amountSource: string (fixed|user_entered|provider_query), billable: boolean, priceAmount: integer|null (minor units, kobo), priceCurrency: string|null, schemaVersion: string
Response 201: capability: Capability (status pending)
Errors: 401 (unauthenticated), 403 (role or MFA missing), 404 (unknown provider), 409 (duplicate capability or claimed service), 422 (invalid schema or component outside client catalogue)

### C-015: GET /v1/capabilities/{capabilityId}
Status: Implemented
Auth: Session cookie (internal services); operator session + MFA for review surface
Request: —
Response 200: capability: Capability, healthStatus: string (healthy|degraded|unavailable)
Errors: 401 (unauthenticated), 404 (unknown capability)

### C-016: POST /v1/capabilities/{capabilityId}/review
Status: Implemented
Auth: Operator session cookie + MFA, role provider review analyst
Request: decision: string (approve|reject|quarantine|deregister), reason: string|null, schemaVersion: string
Response 200: capability: Capability (status active|withdrawn|quarantined)
Errors: 401 (unauthenticated), 403 (role or MFA missing), 404 (unknown capability), 409 (capability not pending, or schema version mismatch)

## Phase 2: The payment loop

Numbering continues from C-016. Amounts are integer minor units
(kobo). Money movements require an `Idempotency-Key` header.

### C-017: POST /v1/payments/authorise
Status: Frozen
Auth: Session cookie (authenticated account owner)
Request: serviceId: string, amount: integer (minor units, kobo), currency: string (NGN), payeeReference: string|null, paymentMethodId: string|null, channel: string (app|ussd|sms|whatsapp), secondConfirmation: boolean (required true above the user's set limit)
Response 201: paymentId: string, status: string (initiated|authorized|pending|succeeded|failed|reversed|refunded), mandateId: string, railReference: string|null
Errors: 400 (invalid amount or missing second confirmation), 401 (unauthenticated), 402 (insufficient funds or limit), 409 (duplicate authorisation; returns the existing paymentId and reference), 422 (amount above limit without confirmation)

### C-018: POST /v1/payments/{paymentId}/execute
Status: Frozen
Auth: Session cookie (authenticated account owner)
Request: mandateId: string, Idempotency-Key header
Response 200: paymentId: string, status: string, railReference: string|null
Errors: 401 (unauthenticated), 404 (unknown payment), 409 (mandate already consumed or duplicate key), 410 (mandate expired), 422 (mandate does not bind the amount and payee)

### C-019: GET /v1/payments
Status: Frozen
Auth: Session cookie (authenticated account owner)
Request: cursor: string|null, limit: integer (default 20), status: string|null
Response 200: payments: PaymentSummary[], nextCursor: string|null
Errors: 401 (unauthenticated), 429 (rate limited)
PaymentSummary: paymentId: string, serviceId: string, amount: integer, currency: string, payee: string, status: string, channel: string, createdAt: string, updatedAt: string

### C-020: POST /v1/identity/verifications
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: method: string (nin|bvn), identifier: string
Response 202: verificationId: string, status: string (pending|verified|failed|corrected)
Errors: 400 (invalid identifier), 401 (unauthenticated), 409 (verification already in progress)

### C-021: GET /v1/identity/verifications/{verificationId}
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: verificationId: string, method: string, status: string, reason: string|null, verifiedAt: string|null
Errors: 401 (unauthenticated), 404 (unknown verification)

### C-022: GET /v1/account/verification
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: kycStatus: string (unverified|pending|verified|rejected), method: string|null, canCorrect: boolean
Errors: 401 (unauthenticated)

### C-023: GET /v1/receipts
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: q: string|null, cursor: string|null, limit: integer (default 20)
Response 200: receipts: ReceiptSummary[], nextCursor: string|null
Errors: 401 (unauthenticated), 429 (rate limited)
ReceiptSummary: receiptId: string, paymentId: string, reference: string, payee: string, amount: integer, currency: string, kind: string (official_e_receipt|biller_confirmation|token), status: string, issuedAt: string|null

### C-024: GET /v1/receipts/{receiptId}
Status: Implemented (revision 2)
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: receipt: Receipt (includes unverifiedReason: string|null), payment: PaymentSummary
Errors: 401 (unauthenticated), 404 (unknown receipt)

### C-025: GET /v1/receipts/{receiptId}/document
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: documentRef: string, contentType: string, shareToken: string|null
Errors: 401 (unauthenticated), 404 (unknown receipt), 409 (receipt awaiting the source document)

### C-026: GET /v1/cases
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: cursor: string|null, limit: integer (default 20), status: string|null
Response 200: cases: CaseSummary[], nextCursor: string|null
Errors: 401 (unauthenticated), 429 (rate limited)
CaseSummary: caseId: string, paymentId: string, type: string (failed_no_delivery|disputed|refund|receipt_missing), status: string (open|awaiting_provider|resolved|escalated|closed), openedAt: string, updatedAt: string

### C-027: GET /v1/cases/{caseId}
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: case: PaymentCase, payment: PaymentSummary, timeline: PaymentEvent[]
Errors: 401 (unauthenticated), 404 (unknown case)

### C-028: POST /v1/cases/{caseId}/dispute
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: reason: string
Response 201: caseId: string, status: string, openedAt: string
Errors: 401 (unauthenticated), 404 (unknown case), 409 (a dispute already exists for this payment)

### C-029: POST /v1/payments/{paymentId}/refund
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: reason: string, Idempotency-Key header
Response 202: paymentId: string, status: string (reversed|refunded), refundReference: string|null
Errors: 401 (unauthenticated), 404 (unknown payment), 409 (duplicate refund for the reference), 422 (payment not refundable in its current state), 503 (the rail did not settle the refund; retryable)

### C-030: POST /v1/payments/federal/prepare
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: serviceId: string, payerReference: string|null
Response 200: serviceId: string, collectingBody: string, amount: integer|null, currency: string, requiresReference: boolean, instructions: string|null
Errors: 400 (invalid service), 401 (unauthenticated), 409 (agency collection account changed; re-resolve), 422 (service not a federal collection)

### C-031: GET /v1/payments/federal/{paymentId}/receipt
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: —
Response 202: status: string (awaiting_receipt), retryAfterSeconds: integer
Response 200: receiptId: string, receiptNumber: string, verificationStatus: string (verified|unverified|pending)
Errors: 401 (unauthenticated), 404 (unknown payment), 409 (payment did not succeed)

### C-032: POST /v1/payments/federal/{paymentId}/reconcile
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: reason: string
Response 202: caseId: string, status: string
Errors: 401 (unauthenticated), 404 (unknown payment), 409 (reconciliation case already open)

### C-033: POST /v1/payments/bills/validate
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: serviceId: string, recipientIdentifier: string, amount: integer|null
Response 200: valid: boolean, recipientIdentifier: string, knownAmount: integer|null, currency: string, range: object|null (minimum: integer, maximum: integer; minor units), reason: string|null
Errors: 400 (invalid identifier), 401 (unauthenticated), 404 (unknown service), 503 (biller offline; payment prevented)

### C-034: POST /v1/payments/bills
Status: Implemented
Auth: Session cookie (authenticated account owner)
Request: serviceId: string, recipientIdentifier: string, amount: integer, currency: string (NGN), Idempotency-Key header
Response 201: paymentId: string, status: string, token: string|null, receiptId: string|null
Errors: 400 (invalid input), 401 (unauthenticated), 402 (insufficient funds), 409 (duplicate authorisation), 503 (biller offline)

### C-035: GET /v1/payments/bills/{paymentId}/token
Status: Frozen (revision 1)
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: token: string, receiptId: string
Response 202: status: string (awaiting_token), retryAfterSeconds: integer
Errors: 401 (unauthenticated), 404 (unknown payment), 409 (payment failed; the shared error envelope's details carry status: "failed" and reason: string|null)

### C-036: POST /v1/channels/ussd/session
Status: Implemented
Auth: Channel identity (MSISDN session, no app session)
Request: sessionId: string, msisdn: string, input: string|null, step: string|null
Response 200: prompt: string, step: string, done: boolean
Errors: 400 (invalid session input), 409 (session already open elsewhere), 410 (session timed out; pending payment resumable)

### C-037: POST /v1/channels/ussd/authorise
Status: Implemented
Auth: Channel identity (MSISDN session)
Request: sessionId: string, confirmation: string, Idempotency-Key header
Response 200: status: string (succeeded|pending|failed), reference: string|null
Errors: 400 (invalid confirmation), 409 (duplicate authorisation), 410 (session timed out after authorisation; payment pending)

### C-038: GET /v1/channels/sms/status/{reference}
Status: Frozen (revision 2)
Auth: Channel identity, resolved server-side from the aggregator session or delivery report. The subscriber number is never taken from a client-supplied header: an inbound header is spoofable, so C-038 accepts the MSISDN-bound session established by C-036/C-037 or the aggregator's signed callback context, and an unrecognised caller gets 404.
Request: sessionId: string|null (the MSISDN-bound session from C-036/C-037, when the caller holds one)
Response 200: reference: string, status: string (queued|sent|delivered|failed), token: string|null
Errors: 404 (unknown reference, or no bound session for the caller)

## Phase 1.5: Operations Console

Implemented. Numbering continues from C-038. These are the staff-auth and audit-read surfaces
specified in `docs/Sabi/operations-console.md`.

### C-039: POST /v1/staff/auth/login
Status: Implemented
Auth: None (public staff login; distinct from the end-user passkey flow)
Request: email: string, password: string, totp: string
Response 200: session: HttpOnly Secure SameSite cookie, staff: object (staffId: string, email: string, role: string), mustEnrolMfa: boolean
Errors: 400 (invalid input), 401 (invalid credentials or TOTP), 403 (role not permitted), 423 (account locked after repeated failures), 429 (rate limited)

### C-040: POST /v1/staff/auth/logout
Status: Implemented
Auth: Staff session cookie
Request: —
Response 204: —
Errors: 401 (unauthenticated)

### C-044: GET /v1/staff/auth/session
Status: Implemented
Auth: Staff session cookie (MFA-verified operator session)
Request: —
Response 200: staff: object (staffId: string, email: string, role: string)
Errors: 401 (no live operator session, or the account no longer exists)

### C-041: GET /v1/staff/audit
Status: Implemented
Auth: Staff session cookie + MFA, role compliance_privacy_officer or administrator
Request: actor: string|null, role: string|null, target: string|null, action: string|null, from: string|null, to: string|null, cursor: string|null, limit: integer (default 20)
Response 200: entries: AuditEntry[], nextCursor: string|null
Errors: 401 (unauthenticated), 403 (role or MFA missing), 429 (rate limited)
AuditEntry: auditId: string, actor: string, role: string, target: string, action: string, reason: string|null, occurredAt: string

### C-042: POST /v1/staff/audit/findings/{findingsId}/close
Status: Implemented
Auth: Staff session cookie + MFA, role compliance_privacy_officer
Request: resolution: string
Response 200: findingsId: string, status: string (closed), closedAt: string
Errors: 401 (unauthenticated), 403 (role or MFA missing), 404 (unknown finding), 409 (finding already closed)

### C-043: POST /v1/staff/audit/export
Status: Implemented
Auth: Staff session cookie + MFA, role compliance_privacy_officer
Request: from: string, to: string, format: string (csv|json)
Response 202: exportId: string, status: string (queued)
Errors: 401 (unauthenticated), 403 (role or MFA missing), 422 (range too large)
