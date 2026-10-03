"""Payment case management for failed, disputed, and refunded payments (FEAT-009).

Cases live in the primary store; the payment record and its append-only event
timeline live in the isolated payment store and are reached through the port in
``app.cases.ports``. Nothing here reads payment tables directly, so the payment
module stays behind its boundary (architecture.md).
"""
