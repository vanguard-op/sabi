# Sabi: contracts

One entry per interface. `Frozen` once agreed, `Implemented` once shipped and conformed. A change
after `Frozen` is a change request: mark it `Frozen (revision N)` and re-dispatch both sides.

### C-001: POST /v1/auth/register/options
Status: Frozen
Auth: None (public, unauthenticated)
Request: locale: string (en|pcm)
Response 200: challengeId: string, publicKey: object (WebAuthn PublicKeyCredentialCreationOptions)
Errors: 400 (invalid locale), 429 (rate limited)

### C-002: POST /v1/auth/register/verify
Status: Frozen
Auth: None (public, unauthenticated)
Request: challengeId: string, credential: object (WebAuthn attestation), displayName: string|null, locale: string (en|pcm)
Response 201: user: User, recoveryCode: string (shown once, single-use), session: HttpOnly Secure cookie
Errors: 400 (invalid attestation), 409 (credential already registered), 410 (challenge expired)

### C-003: POST /v1/auth/login/options
Status: Frozen
Auth: None (public, unauthenticated)
Request: —
Response 200: challengeId: string, publicKey: object (WebAuthn PublicKeyCredentialRequestOptions)
Errors: 429 (rate limited)

### C-004: POST /v1/auth/login/verify
Status: Frozen
Auth: None (public, unauthenticated)
Request: challengeId: string, credential: object (WebAuthn assertion)
Response 200: user: User, session: HttpOnly Secure cookie
Errors: 400 (invalid assertion), 401 (no matching credential), 410 (challenge expired)

### C-005: POST /v1/auth/recovery/verify
Status: Frozen
Auth: None (public, unauthenticated)
Request: recoveryCode: string
Response 200: user: User, mustEnrolPasskey: boolean (true), session: HttpOnly Secure cookie
Errors: 401 (invalid code), 409 (code already used)

### C-006: POST /v1/auth/recovery/regenerate
Status: Frozen
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: recoveryCode: string (shown once, single-use)
Errors: 401 (unauthenticated)

### C-007: POST /v1/auth/channel-links
Status: Frozen
Auth: Session cookie (authenticated account owner)
Request: channel: string (ussd|sms|whatsapp), address: string
Response 201: id: string, channel: string, address: string, verifiedAt: string|null
Errors: 409 (address already linked to another account; owner notified), 422 (invalid address)

### C-008: GET /v1/account/me
Status: Frozen
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: id: string, displayName: string|null, locale: string, preferredChannel: string, kycStatus: string, accountStatus: string, channelLinks: array of ChannelLink, createdAt: string, updatedAt: string
Errors: 401 (unauthenticated)

### C-009: POST /v1/agent/intents
Status: Frozen (revision 2)
Auth: Session cookie (authenticated account owner)
Request: text: string (non-empty, max 200 chars), locale: string (en|pcm), channel: string (app|ussd|sms|whatsapp)
Response 200: intent: object (intentType: string, target: string|null, amount: integer|null (minor units, kobo), currency: string, reference: string|null, constraints: object, confidence: number, language: string, clarifyingQuestion: string|null), candidates: ServiceSummary[], source: string (model|fallback)
Errors: 400 (empty or oversized text), 429 (rate limited)

### C-010: GET /v1/catalogue/search
Status: Frozen (revision 2)
Auth: Session cookie (authenticated account owner)
Request: q: string (non-empty, max 200 chars), category: string|null, limit: integer (default 5, max 5)
Response 200: results: ServiceSummary[], noMatch: boolean
Errors: 400 (missing or over-length q), 429 (rate limited)
ServiceSummary: serviceId: string, name: string, collectingBody: string, category: string, knownAmount: integer|null (minor units, kobo), currency: string, status: string, confidence: number

### C-011: GET /v1/catalogue/services/{serviceId}
Status: Frozen
Auth: Session cookie (authenticated account owner)
Request: —
Response 200: service: Service
Errors: 404 (unknown service)

### C-012: POST /v1/agent/surfaces
Status: Frozen
Auth: Session cookie (authenticated account owner)
Request: task: string (confirmation|amount_entry|receipt|discovery), context: object
Response 200: messages: array of object (declarative UI messages: createSurface | updateComponents | updateDataModel), fallback: string (task key)
Errors: 200 with fallback on invalid composition, 400 (unknown task), 429 (rate limited)

### C-013: POST /v1/providers
Status: Frozen
Auth: Operator session cookie + MFA, role provider review analyst
Request: name: string, type: string (agency|biller|merchant|aggregator), contactEmail: string
Response 201: provider: Provider (status pending)
Errors: 401 (unauthenticated), 403 (role or MFA missing), 409 (duplicate provider), 422 (invalid input)

### C-014: POST /v1/providers/{providerId}/capabilities
Status: Frozen
Auth: Operator session cookie + MFA, role provider review analyst
Request: name: string, serviceId: string|null, inputSchemaRef: string, amountSource: string (fixed|user_entered|provider_query), billable: boolean, priceAmount: integer|null (minor units, kobo), priceCurrency: string|null, schemaVersion: string
Response 201: capability: Capability (status pending)
Errors: 401 (unauthenticated), 403 (role or MFA missing), 404 (unknown provider), 409 (duplicate capability or claimed service), 422 (invalid schema or component outside client catalogue)

### C-015: GET /v1/capabilities/{capabilityId}
Status: Frozen
Auth: Session cookie (internal services); operator session + MFA for review surface
Request: —
Response 200: capability: Capability, healthStatus: string (healthy|degraded|unavailable)
Errors: 401 (unauthenticated), 404 (unknown capability)

### C-016: POST /v1/capabilities/{capabilityId}/review
Status: Frozen
Auth: Operator session cookie + MFA, role provider review analyst
Request: decision: string (approve|reject|quarantine|deregister), reason: string|null, schemaVersion: string
Response 200: capability: Capability (status active|withdrawn|quarantined)
Errors: 401 (unauthenticated), 403 (role or MFA missing), 404 (unknown capability), 409 (capability not pending, or schema version mismatch)
