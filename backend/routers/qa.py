"""Trust-pipeline endpoints: operator approvals (and, later, reliability stats).

POST approvals validate that the image_id actually belongs to the project
(GT-005) — the current replica or any current result record. Approval writes
never touch a running generation: revocation applies at the next gate check
(there is no mid-run cancel by design; the batch's spend is already consented).
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request

from backend.models import ApprovalRequest, ApprovalResponse, ProjectResponse
from backend.qa.approvals import Approval, get_approval_store
from backend.qa.qa_lane import get_qa_lane
from backend.qa.reliability import aggregate, append_record
from backend.qa.styles_classes import style_class
from backend.routers.projects_common import (
    get_project_or_404,
    get_store,
    to_project_response,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/projects/{project_id}/approvals", response_model=ProjectResponse)
def set_approval(
    project_id: str, body: ApprovalRequest, request: Request
) -> ProjectResponse:
    store = get_store(request)
    project = get_project_or_404(store, project_id)

    if body.image_id == project.base_image_id:
        kind = "replica"
    elif any(r.image_id == body.image_id for r in project.results):
        kind = "variant"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"GT-005: image {body.image_id!r} is not part of this project",
        )

    try:
        get_approval_store().set(
            Approval(
                image_id=body.image_id,
                project_id=project_id,
                kind=kind,
                verdict=body.verdict,
                reasons=body.reasons,
                note=body.note,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Ledger: score this human verdict against the pipeline's, captured at
    # decision time (null if QA hadn't finished). Ordered writes — a ledger
    # failure is logged and MUST NOT roll back the approval.
    try:
        verdict = project.qa_verdicts.get(body.image_id) or {}
        pipeline_verdict = (
            verdict.get("verdict") if verdict.get("qa_status") == "done" else None
        )
        append_record(
            image_id=body.image_id,
            project_id=project_id,
            kind=kind,
            style_class=style_class(project.door_style),
            pipeline_verdict=pipeline_verdict,
            human_verdict=body.verdict,
            reasons=body.reasons,
        )
    except OSError:
        logger.exception("reliability ledger append failed for %s", body.image_id)

    # Pin migrated identities: saving persists any load-generated image_ids
    # so the approval still points at this image after a restart.
    store.save(project_id)
    return to_project_response(get_project_or_404(store, project_id))


@router.post(
    "/projects/{project_id}/images/{image_id}/rejudge",
    response_model=ProjectResponse,
)
def rejudge_image(
    project_id: str,
    image_id: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> ProjectResponse:
    """Re-enqueue QA for one image (e.g. after an error verdict)."""
    store = get_store(request)
    project = get_project_or_404(store, project_id)

    if image_id == project.base_image_id:
        kind = "replica"
    elif any(r.image_id == image_id for r in project.results):
        kind = "variant"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"GT-005: image {image_id!r} is not part of this project",
        )

    get_qa_lane().enqueue(store, project_id, image_id, x_api_key, kind=kind)
    return to_project_response(get_project_or_404(store, project_id))


@router.get("/qa/reliability")
def reliability_stats() -> dict:
    """Pipeline-vs-operator agreement — the evidence for bulk unlock."""
    return aggregate()


@router.get("/projects/{project_id}/approvals", response_model=list[ApprovalResponse])
def list_approvals(project_id: str, request: Request) -> list[ApprovalResponse]:
    store = get_store(request)
    get_project_or_404(store, project_id)
    return [
        ApprovalResponse(
            image_id=a.image_id,
            project_id=a.project_id,
            kind=a.kind,
            verdict=a.verdict,
            reasons=a.reasons,
            note=a.note,
            decided_at=a.decided_at,
        )
        for a in get_approval_store().for_project(project_id)
    ]
