/// The Sabi A2UI catalog document, as pure data (FEAT-011, C-012 revision 2).
///
/// This is the single authored catalog: a standalone JSON Schema whose `$id`
/// and `catalogId` are [sabiCatalogId] and whose `components` are the composed
/// task surfaces the client renders. Both sides derive from it — the client's
/// [SabiCatalog] re-exports it for validation and the agent-side pre-send check,
/// and `services/ai/core/catalogs/sabi_a2ui_v1.json` is generated from it at
/// build time by `generate_catalog.dart`.
///
/// It lives apart from `sabi_catalog.dart` and imports nothing from Flutter so
/// the generator can run under plain `dart run` and emit the JSON the AI service
/// ships (A2UI: the catalog is a deploy-time artifact known to both sides, never
/// fetched at runtime).
library;

/// The catalog URI. Per A2UI, `catalogId` and the schema document's `$id` are
/// the same URI; the major version is carried in the path (v1) and the catalog
/// evolves additively within it (A2UI "Catalog Naming & Versioning").
const String sabiCatalogId = 'https://sabi.app/a2ui/v1/catalog.json';

/// The published catalog document.
///
/// A2UI catalogs must be freestanding (no external `$ref`s), so this is the
/// exact document the agent composes against and the client validates with.
/// The map preserves insertion order, so `components` is in catalog order.
Map<String, Object?> buildSabiCatalogDocument() => {
  r'$schema': 'https://json-schema.org/draft/2020-12/schema',
  r'$id': sabiCatalogId,
  'catalogId': sabiCatalogId,
  'title': 'Sabi A2UI Catalog',
  'description':
      'The Sabi client composed-surface catalog: the confirmation summary, '
      'amount entry, provider picker, service result row, receipt card, '
      'status pill, verification, and recovery surfaces (FEAT-011).',
  'components': {
    'ConfirmationSummary': {
      'type': 'object',
      'description':
          'A payment confirmation: amount, payee, charges, and reference.',
      'properties': {
        'amount': {'type': 'integer', 'description': 'Minor units (kobo).'},
        'currency': {'type': 'string', 'default': 'NGN'},
        'payee': {'type': 'string'},
        'charges': {'type': ['integer', 'null']},
        'reference': {'type': ['string', 'null']},
      },
      'required': ['amount', 'payee'],
      'additionalProperties': true,
    },
    'AmountEntry': {
      'type': 'object',
      'description':
          'Requests a variable amount for the resolved obligation.',
      'properties': {
        'currency': {'type': 'string', 'default': 'NGN'},
        'minimum': {'type': ['integer', 'null']},
        'maximum': {'type': ['integer', 'null']},
        'prompt': {'type': ['string', 'null']},
      },
      'required': [],
      'additionalProperties': true,
    },
    'ProviderPicker': {
      'type': 'object',
      'description':
          'A choice among several matching collecting bodies. Each service '
          'is a ServiceResultRow-shaped object.',
      'properties': {
        'services': {
          'type': 'array',
          'items': {r'$ref': '#/components/ServiceResultRow'},
        },
      },
      'required': ['services'],
      'additionalProperties': true,
    },
    'ServiceResultRow': {
      'type': 'object',
      'description': 'One discovery result: collecting body and obligation.',
      'properties': {
        'serviceId': {'type': 'string'},
        'name': {'type': 'string'},
        'collectingBody': {'type': 'string'},
        'category': {'type': 'string'},
        'knownAmount': {'type': ['integer', 'null']},
        'currency': {'type': 'string', 'default': 'NGN'},
        'status': {'type': 'string', 'default': 'active'},
        'confidence': {'type': 'number'},
      },
      'required': ['serviceId', 'collectingBody', 'category'],
      'additionalProperties': true,
    },
    'ReceiptCard': {
      'type': 'object',
      'description': 'A resolved record or post-payment receipt.',
      'properties': {
        'receiptId': {'type': 'string'},
        'reference': {'type': 'string'},
        'payee': {'type': 'string'},
        'amount': {'type': 'integer', 'description': 'Minor units (kobo).'},
        'currency': {'type': 'string', 'default': 'NGN'},
        'issuedAt': {'type': 'string'},
        'kind': {'type': 'string'},
        'status': {'type': 'string'},
      },
      'required': ['reference', 'payee', 'amount'],
      'additionalProperties': true,
    },
    'StatusPill': {
      'type': 'object',
      'description':
          'A payment state. Colour is never the only signal: the pill pairs '
          'a semantic colour with a glyph and a label.',
      'properties': {
        'status': {
          'type': 'string',
          'description':
              'Open enum: pending, settled, failed, awaitingReceipt, '
              'unverified, verified, suspended. Unknown variants render as '
              'pending (A2UI open enums).',
        },
        'label': {'type': ['string', 'null']},
      },
      'required': ['status'],
      'additionalProperties': true,
    },
    'Verification': {
      'type': 'object',
      'description':
          'An identity-verification task held in the conversation. The task '
          'is held, not failed, and resumes once verification succeeds.',
      'properties': {
        'title': {'type': 'string'},
        'body': {'type': ['string', 'null']},
        'actionLabel': {'type': ['string', 'null']},
      },
      'required': ['title'],
      'additionalProperties': true,
    },
    'Recovery': {
      'type': 'object',
      'description':
          'A failed-payment or case recovery task: the current state and '
          'the next step.',
      'properties': {
        'title': {'type': 'string'},
        'body': {'type': ['string', 'null']},
        'status': {'type': ['string', 'null']},
        'actionLabel': {'type': ['string', 'null']},
      },
      'required': ['title'],
      'additionalProperties': true,
    },
  },
  'styles': <String, Object?>{},
  'functions': <String, Object?>{},
};
