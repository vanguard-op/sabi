"""Provider registration, capability submission, and review (FEAT-012, C-013–C-016).

The service owns the review workflow from operations.md: a submission is
validated, reviewed by a provider review analyst, and only then activated. Every
privileged action is appended to the tamper-evident audit log with the actor,
role, target, and reason (NFR-028); personal data such as the provider contact
email is never written to the log.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.audit import AuditLog
from app.core.errors import APIError, ErrorCode
from app.core.sessions import SessionData
from app.core.time import to_rfc3339
from app.db.models import Capability, Provider, Service
from app.registry.catalogue import DEFAULT_SCHEMA_CATALOG, SchemaCatalog
from app.registry.repository import (
    find_live_capability_by_name,
    find_live_capability_by_service,
    find_provider_by_name,
    get_capability,
    get_provider,
    get_service,
    list_provider_capabilities,
)
from app.registry.schemas import (
    AmountSource,
    CapabilityCreateRequest,
    ProviderCreateRequest,
    ReviewDecision,
)


# --------------------------------------------------------------------------- #
# Wire mapping
# --------------------------------------------------------------------------- #
def provider_payload(provider: Provider) -> dict:
    return {
        "id": provider.id,
        "name": provider.name,
        "type": provider.type,
        "contactEmail": provider.contact_email,
        "status": provider.status,
        "createdAt": to_rfc3339(provider.created_at),
    }


def capability_payload(capability: Capability) -> dict:
    return {
        "id": capability.id,
        "providerId": capability.provider_id,
        "serviceId": capability.service_id,
        "name": capability.name,
        "inputSchemaRef": capability.input_schema_ref,
        "amountSource": capability.amount_source,
        "billable": capability.billable,
        "priceAmount": capability.price_amount,
        "priceCurrency": capability.price_currency,
        "schemaVersion": capability.schema_version,
        "healthStatus": capability.health_status,
        "status": capability.status,
        "createdAt": to_rfc3339(capability.created_at),
    }


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
def create_provider(
    db: Session,
    audit: AuditLog,
    *,
    actor: SessionData,
    request: ProviderCreateRequest,
) -> Provider:
    if find_provider_by_name(db, request.name) is not None:
        raise APIError(409, ErrorCode.CONFLICT, "A provider with this name already exists.")

    provider = Provider(
        name=request.name,
        type=request.type.value,
        contact_email=str(request.contact_email),
        status="pending",
    )
    db.add(provider)
    db.flush()

    audit.append(
        "provider.create",
        actor_id=actor.user_id,
        actor_role=actor.role,
        target=provider.id,
        # contactEmail is personal data (schema.md); it is not logged.
        detail={"name": provider.name, "type": provider.type},
    )
    return provider


def create_capability(
    db: Session,
    audit: AuditLog,
    *,
    actor: SessionData,
    provider_id: str,
    request: CapabilityCreateRequest,
    schema_catalog: SchemaCatalog | None = None,
) -> Capability:
    provider = get_provider(db, provider_id)
    if provider is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "That provider does not exist.")

    catalog = schema_catalog or DEFAULT_SCHEMA_CATALOG
    catalog.validate(request.input_schema_ref)

    service = _service_for_capability(db, request)
    _assert_amount_is_handled(request, service)
    _assert_not_duplicate(db, provider, service, request)

    capability = Capability(
        provider_id=provider.id,
        service_id=service.id if service is not None else None,
        name=request.name,
        input_schema_ref=request.input_schema_ref,
        amount_source=request.amount_source.value,
        billable=request.billable,
        price_amount=request.price_amount,
        price_currency=request.price_currency,
        schema_version=request.schema_version,
        health_status="healthy",
        status="pending",
    )
    db.add(capability)
    db.flush()

    # A capability is the provider's claim on a service; record it so a second
    # provider cannot claim the same service (FEAT-012).
    if service is not None and service.provider_id is None:
        service.provider_id = provider.id

    audit.append(
        "capability.create",
        actor_id=actor.user_id,
        actor_role=actor.role,
        target=capability.id,
        detail={
            "providerId": provider.id,
            "serviceId": capability.service_id,
            "schemaVersion": capability.schema_version,
            "amountSource": capability.amount_source,
        },
    )
    return capability


def _service_for_capability(db: Session, request: CapabilityCreateRequest) -> Service | None:
    if request.service_id is None:
        return None
    service = get_service(db, request.service_id)
    if service is None:
        raise APIError(422, ErrorCode.VALIDATION_FAILED, "The referenced service does not exist.")
    return service


def _assert_amount_is_handled(request: CapabilityCreateRequest, service: Service | None) -> None:
    if request.amount_source is AmountSource.FIXED:
        # Operations.md: a fixed amount must be stated in minor units, which
        # means the mapped service must carry a known amount.
        if service is None:
            raise APIError(
                422,
                ErrorCode.VALIDATION_FAILED,
                "A fixed amount needs a service with a known amount.",
            )
        if service.known_amount is None:
            raise APIError(
                422,
                ErrorCode.VALIDATION_FAILED,
                "A fixed amount must be stated in minor units.",
            )

    if request.billable:
        if request.price_amount is None or request.price_currency is None:
            raise APIError(
                422,
                ErrorCode.VALIDATION_FAILED,
                "A billable capability needs a price and a currency.",
            )
    elif request.price_amount is not None or request.price_currency is not None:
        raise APIError(
            422,
            ErrorCode.VALIDATION_FAILED,
            "A non-billable capability cannot carry a price.",
        )


def _assert_not_duplicate(
    db: Session,
    provider: Provider,
    service: Service | None,
    request: CapabilityCreateRequest,
) -> None:
    if find_live_capability_by_name(db, provider.id, request.name) is not None:
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "This capability name is already registered for this provider.",
        )

    if service is None:
        return

    claimed = find_live_capability_by_service(db, service.id)
    if claimed is not None:
        raise APIError(409, ErrorCode.CONFLICT, "This service is already claimed.")
    if service.provider_id is not None and service.provider_id != provider.id:
        # Two providers claim the same service; ownership is resolved before
        # any activation (FEAT-012).
        raise APIError(409, ErrorCode.CONFLICT, "This service is claimed by another provider.")


# --------------------------------------------------------------------------- #
# Review
# --------------------------------------------------------------------------- #
def review_capability(
    db: Session,
    audit: AuditLog,
    *,
    actor: SessionData,
    capability_id: str,
    decision: ReviewDecision,
    reason: str | None,
    schema_version: str,
) -> Capability:
    capability = get_capability(db, capability_id)
    if capability is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "That capability does not exist.")
    if capability.status != "pending":
        raise APIError(409, ErrorCode.CONFLICT, "This capability is not awaiting review.")
    if schema_version != capability.schema_version:
        # The reviewer must approve the version that was actually submitted; an
        # incompatible change waits for its own review (FEAT-012).
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "The reviewed schema version does not match the submitted version.",
        )

    from_status = capability.status
    service = get_service(db, capability.service_id) if capability.service_id else None
    provider = get_provider(db, capability.provider_id)

    if decision is ReviewDecision.APPROVE:
        capability.status = "active"
        if provider is not None and provider.status == "pending":
            provider.status = "active"
        if service is not None:
            service.capability_id = capability.id
    elif decision is ReviewDecision.REJECT:
        # A rejected submission can be corrected and resubmitted (operations.md).
        capability.status = "withdrawn"
    elif decision is ReviewDecision.QUARANTINE:
        # A forged or missing result removes the capability from discovery and
        # opens a review; evidence is the audit entry (FEAT-012).
        capability.status = "quarantined"
        capability.health_status = "unavailable"
        if service is not None and service.capability_id == capability.id:
            service.capability_id = None
    elif decision is ReviewDecision.DEREGISTER:
        # Deregistration stops offering the provider's capabilities but keeps
        # the records for reconciliation and audit (FEAT-012, operations.md).
        capability.status = "withdrawn"
        capability.health_status = "unavailable"
        if service is not None and service.capability_id == capability.id:
            service.capability_id = None
        if provider is not None:
            provider.status = "deregistered"
            for other in list_provider_capabilities(db, provider.id):
                if other.id == capability.id or other.status not in (
                    "pending",
                    "active",
                    "quarantined",
                ):
                    continue
                other.status = "withdrawn"
                other.health_status = "unavailable"
                if other.service_id is not None:
                    other_service = get_service(db, other.service_id)
                    if other_service is not None and other_service.capability_id == other.id:
                        other_service.capability_id = None

    db.flush()

    audit.append(
        "capability.review",
        actor_id=actor.user_id,
        actor_role=actor.role,
        target=capability.id,
        reason=reason,
        detail={
            "decision": decision.value,
            "fromStatus": from_status,
            "toStatus": capability.status,
            "schemaVersion": schema_version,
            "providerId": capability.provider_id,
        },
    )
    return capability


def get_capability_or_404(db: Session, capability_id: str) -> Capability:
    capability = get_capability(db, capability_id)
    if capability is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "That capability does not exist.")
    return capability


__all__ = [
    "capability_payload",
    "create_capability",
    "create_provider",
    "get_capability_or_404",
    "provider_payload",
    "review_capability",
]
