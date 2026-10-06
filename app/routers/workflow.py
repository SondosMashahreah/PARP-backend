from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.workflow import (
    AcceptReviewRequest,
    AffiliationRequest,
    AssignReviewerRequest,
    DecisionRequest,
    RecommendationStatusRequest,
    ReviewRequest,
    UserAccessUpdate,
)
from app.services import workflow


router = APIRouter(prefix="/api/workflow", tags=["PARP workflow"])


@router.get("/workspace")
def role_workspace(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.workspace(db, current_user)


@router.patch("/me/affiliation")
def request_affiliation(
    data: AffiliationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.set_affiliation_request(db, current_user, data)


@router.post("/affiliations/{user_id}/approve")
def approve_affiliation(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.approve_affiliation(db, current_user, user_id)


@router.post("/research")
async def submit_research(
    title: str = Form(..., min_length=2, max_length=500),
    research_field: str = Form(..., min_length=2, max_length=150),
    problem: str = Form(..., min_length=2, max_length=12000),
    recommendations: str = Form("", max_length=12000),
    abstract: str = Form("", max_length=12000),
    form_json: str = Form("{}"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await file.read(workflow.MAX_RESEARCH_BYTES + 1)
    return workflow.create_submission(
        db,
        current_user,
        title=title,
        research_field=research_field,
        problem=problem,
        recommendations=recommendations,
        abstract=abstract,
        form_json=form_json,
        file_name=file.filename or "research",
        content_type=file.content_type or "",
        file_bytes=data,
    )


@router.post("/research/{submission_id}/resubmit")
async def resubmit_research(
    submission_id: int,
    form_json: str = Form("{}"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await file.read(workflow.MAX_RESEARCH_BYTES + 1)
    return workflow.resubmit(
        db,
        current_user,
        submission_id,
        form_json=form_json,
        file_name=file.filename or "research",
        content_type=file.content_type or "",
        file_bytes=data,
    )


@router.post("/research/{submission_id}/assign-reviewer")
def assign_reviewer(
    submission_id: int,
    data: AssignReviewerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.assign_reviewer(db, current_user, submission_id, data.reviewer_id)


@router.post("/assignments/{assignment_id}/accept")
def accept_review(
    assignment_id: int,
    data: AcceptReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.accept_assignment(
        db, current_user, assignment_id, data.confidentiality_accepted
    )


@router.post("/assignments/{assignment_id}/review")
def submit_review(
    assignment_id: int,
    data: ReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.submit_review(db, current_user, assignment_id, data)


@router.post("/research/{submission_id}/decision")
def decide_research(
    submission_id: int,
    data: DecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.scientific_decision(db, current_user, submission_id, data)


@router.post("/research/{submission_id}/publish")
def publish_research(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.publish_research(db, current_user, submission_id)


@router.post("/research/{submission_id}/publish-practice")
def publish_practice(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.publish_as_practice(db, current_user, submission_id)


@router.get("/profile/research")
def my_publications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.profile_publications(db, current_user)


@router.get("/repository")
def repository(db: Session = Depends(get_db)):
    return workflow.public_repository(db, "research")


@router.get("/practices")
def practices(db: Session = Depends(get_db)):
    return workflow.public_repository(db, "practice")


@router.get("/observatory/recommendations")
def observatory_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.recommendations(db, current_user)


@router.patch("/observatory/recommendations/{recommendation_id}")
def update_recommendation(
    recommendation_id: int,
    data: RecommendationStatusRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.update_recommendation_status(
        db, current_user, recommendation_id, data.status
    )


@router.get("/problem-bank")
def problem_bank(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.problems(db, current_user)


@router.patch("/admin/users/{user_id}")
def update_user_access(
    user_id: int,
    data: UserAccessUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workflow.update_user_access(db, current_user, user_id, data)
