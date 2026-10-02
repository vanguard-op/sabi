"""FastAPI dependency wiring for the gateway agent module."""

from __future__ import annotations

from fastapi import Request

from app.agent.client import AgentAIClient


def get_agent_client(request: Request) -> AgentAIClient:
    """The process-wide AI service client, built by the app factory.

    Exposed as a dependency so a test can substitute a deterministic double via
    ``app.dependency_overrides`` without a running AI service.
    """

    return request.app.state.agent_ai_client
