# Sabi

A conversational agent that finds, pays for, and stores verifiable receipts for Nigerian government
services and everyday bills — on the phone a user already owns.

## What it does

Sabi is not a chatbot bolted onto a payment form. It resolves what you are trying to do, checks it
with you, takes the money through an isolated payment service, and hands back a receipt you can
prove later. It works in English and Pidgin, over the app, USSD/SMS, and WhatsApp, against one
account and one agent.

## How the agent is built

- **Intent resolution and multi-turn clarification** — "pay my water bill" is not an instruction
  until the agent knows which bill, which account, and how much
- **A hard confirmation gate** — nothing is charged without an explicit confirmation step; the agent
  cannot talk itself past it
- **Catalogue-negotiated UI** — the agent produces A2UI surfaces that Flutter GenUI renders natively,
  so the interface is generated per request rather than hardcoded per provider
- **Grounded answers** — responses are retrieved from catalogue, receipt, and account records through
  pgvector, not recalled from the model
- **Passkey onboarding, with NIN/BVN verification** gating regulated payments

## Payments are isolated on purpose

The agent never moves money directly. A separate payment service owns:

- signed mandates
- idempotency keys
- an explicit payment state machine
- no partial debits
- its own audit log

If the conversational layer is compromised or confused, the blast radius stops at the payment
boundary.

## Structure

```
services/ai        agent orchestration, grounding, catalogue negotiation
services/api       public API
services/payments  mandates, state machine, audit
apps/mobile        Flutter client (Riverpod, go_router, GenUI)
apps/console       staff operations console
infra/terraform    AWS infrastructure
infra/terraform-gcp
migrations/
```

## Getting started

```bash
make setup      # create .env from the template
make up         # start Postgres (with pgvector) and Redis, wait for healthy
make migrate    # apply migrations
make backend-dev
```

`make help` lists every target — build, test, lint, mobile, and the Terraform flows. The Makefile is
the single source of truth: it runs the same locally and in CI.

Tests are split by layer, including `make test-model-quality` for evaluating agent behaviour rather
than only code correctness.

## Staff console

Regulated payments need human oversight somewhere. The console covers provider review, schema
review, quarantine of a misbehaving provider, and an audit trail of privileged actions.

## Status

Active development. Payment isolation and the agent pipeline are implemented; the catalogue coverage
of government services is expanding provider by provider.
