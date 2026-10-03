"""Reconciliation and refund jobs (FEAT-006, FEAT-007, FEAT-009).

This package is a job and service layer, not an HTTP surface: it has no router
and is reached by the scheduler (``app.reconciliation.jobs.run_scheduled_jobs``)
and by other modules. It is listed in ``MODULE_NAMES`` in the app factory but
declared routerless through ``ROUTERLESS_MODULES``, so the module inventory
matches the landed packages while the guard skips this one's absent router by
declaration. It reads the primary store's case table to keep an exception cased
once and crosses to the isolated payment module only through the shared port in
:mod:`app.payments_port`.

Layout:

- ``jobs``: the scheduled entry points and the reconciliation run.
- ``rules``: pure correlation and mismatch decisions (FEAT-006, FEAT-009).
- ``refunds``: automatic refund, duplicate prevention, and settlement tracking
  (FEAT-009).
- ``windows``: case service-window escalation (FEAT-009).
- ``repository``: the primary-store case lookups the jobs own.
- ``ports``: the rail/agency statement, payment, and notification boundaries.
"""
