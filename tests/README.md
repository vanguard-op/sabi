# Integration and acceptance tests

The cross-service layer: it proves the delivered whole meets the frozen contracts
(CONTRACTS.md) and the phase's acceptance criteria, where the per-service unit
suites prove module internals.

The API half checks the full C-001..C-016 set against the assembled service,
including the gateway agent paths C-009 and C-012 that the client actually calls
(architecture.md makes the gateway the sole entry point). The gateway's AI-service
client is a deterministic double, so the agent surface is exercised without a
running AI service or model provider.

The API service and the AI service each expose a top-level `app` package, so they
cannot be imported in one interpreter. The two directories are therefore run as
separate processes:

    # API service: identity, catalogue, provider registry
    (cd services/api && .venv/bin/python -m pytest ../../tests/api)

    # AI service: intent, ranking, composition, model-quality attestation
    (cd services/ai && .venv/bin/python -m pytest ../../tests/ai)

`services/api/.venv` and `services/ai/.venv` both carry pytest; either works for its
own directory. Nothing here needs Postgres, Redis, or a model provider.

`tests/ai/test_model_quality_attestation.py` intentionally fails: it records that
the MQ-001/MQ-001R/MQ-002/MQ-002R/MQ-003/MQ-004 golden-set and reply-rubric
evaluation harness required by model-quality.md is not present in this delivery,
so the judged bars are unverified.
