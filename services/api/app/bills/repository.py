"""Primary-store queries for the everyday-bill flows.

The payable service is the shared catalogue entity, read here rather than
copied (FEAT-007). A captured token receipt is read by its payment and owner so
the token endpoint never exposes another account's token; the payment itself is
read across the isolated store boundary through :mod:`app.bills.ports`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Receipt, Service

# A token product's proof is stored as a ``token`` receipt; its ``document_ref``
# carries the token itself, which is what the client redeems.
TOKEN_KIND = "token"


def get_service(db: Session, service_id: str) -> Service | None:
    return db.get(Service, service_id)


def get_token_receipt(db: Session, *, payment_id: str, user_id: str) -> Receipt | None:
    """The token proof captured for a payment, if one exists."""
    return db.execute(
        select(Receipt)
        .where(
            Receipt.payment_id == payment_id,
            Receipt.user_id == user_id,
            Receipt.kind == TOKEN_KIND,
        )
        .order_by(Receipt.created_at.asc(), Receipt.id.asc())
        .limit(1)
    ).scalar_one_or_none()


__all__ = ["TOKEN_KIND", "get_service", "get_token_receipt"]
