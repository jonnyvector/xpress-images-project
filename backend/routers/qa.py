"""Trust-pipeline endpoints: operator approvals (and, later, reliability stats).

POST approvals validate that the image_id actually belongs to the project
(GT-005) — the current replica or any current result record. Approval writes
never touch a running generation: revocation applies at the next gate check
(there is no mid-run cancel by design; the batch's spend is already consented).
"""

from fastapi import APIRouter, HTTPException, Request

from backend.models import ApprovalRequest, ApprovalResponse, ProjectResponse
from backend.qa.approvals import Approval, get_approval_store
from backend.routers.projects_common import (
    get_project_or_404,
    get_store,
    to_project_response,
)

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

    # Pin migrated identities: saving persists any load-generated image_ids
    # so the approval still points at this image after a restart.
    store.save(project_id)
    return to_project_response(get_project_or_404(store, project_id))


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
