"""API gateway agent module.

The gateway is the client's single entry point (architecture.md, "API Gateway /
Backend-for-Frontend"): it enforces session authentication and rate limiting, then
forwards intent resolution (C-009) and interface composition (C-012) to the AI
service, which owns the model-backed behaviour. The client never reaches the AI
service directly.
"""
