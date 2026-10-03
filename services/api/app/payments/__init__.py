"""API gateway payment module.

The gateway is the client's single entry point (architecture.md, "API Gateway /
Backend-for-Frontend"): it enforces session authentication, rate limiting, and
request validation, resolves the service to its collecting body, then forwards
authorisation (C-017), execution (C-018), and payment listing (C-019) to the
isolated payment module, which owns mandates, the rail, and the payment store.
The client never reaches the payment module directly.

The in-process port in :mod:`app.payment_gateway` stays for same-process
callers; this package is the HTTP edge.
"""
