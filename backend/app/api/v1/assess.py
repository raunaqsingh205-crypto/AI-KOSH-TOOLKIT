import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Union
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_async_db
from app.api.deps import get_current_user, get_user_assessment
from app.models.user import User
from app.models.assessment import Assessment
from app.models.dataset_metadata import DatasetMetadata
from app.schemas.metadata_form import MetadataForm
from app.schemas.assessment import (
    AssessmentSubmitResponse, 
    AssessmentStatusResponse, 
    AssessmentResultResponse,
    UploadUrlRequest, 
    UploadUrlResponse,
    AssessmentSubmitRequest
)
from app.storage.s3_client import s3_client
from app.worker.tasks import run_assessment
from app.audit.logger import audit_logger

router = APIRouter(prefix="/assess", tags=["assessment"])

@router.post(
    "/upload-url",
    response_model=UploadUrlResponse,
    status_code=status.HTTP_201_CREATED
)
async def generate_upload_url(
    req: UploadUrlRequest,
    current_user: User = Depends(get_current_user)
):
    """Generates a pre-signed S3 upload URL for direct client-to-S3 upload."""
    assessment_id = uuid.uuid4()
    file_key = f"uploads/{assessment_id}/{req.filename}"
    upload_url = s3_client.generate_presigned_upload_url(file_key)
    return UploadUrlResponse(
        upload_url=upload_url,
        file_key=file_key,
        assessment_id=assessment_id
    )

@router.post(
    "",
    response_model=AssessmentSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def submit_assessment(
    request: Request,
    req: AssessmentSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Submits a dataset for assessment after the file(s) have been uploaded to S3."""
    
    if not s3_client.file_exists(req.file_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Main dataset file not found in S3. Please upload first."
        )

    try:
        assessment_id = UUID(req.file_key.split("/")[1])
    except (IndexError, ValueError):
        assessment_id = uuid.uuid4()

    dataset_id = req.metadata.aikosh_dataset_id or f"dataset_{uuid.uuid4().hex[:12]}"
    api_key_id = getattr(request.state, "api_key_id", None)
    
    # We infer domain 11 applicability if synthetic_data_pct > 0 or if not explicitly None
    domain_11_app = False
    if req.metadata.synthetic_data_pct is not None and req.metadata.synthetic_data_pct > 0:
        domain_11_app = True
        
    new_assessment = Assessment(
        assessment_id=assessment_id,
        dataset_id=dataset_id,
        user_id=current_user.id,
        api_key_id=api_key_id,
        status="queued",
        toolkit_version="1.1.0",
        domain_11_applicable=domain_11_app,
        assessment_mode="full",
        file_format=req.file_key.split(".")[-1] if "." in req.file_key else "csv",
        file_size_bytes=0, 
        s3_file_key=req.file_key,
        submission_timestamp=datetime.now(timezone.utc)
    )
    db.add(new_assessment)

    form_dict = req.metadata.model_dump(exclude_unset=True)
    form_dict["assessment_id"] = assessment_id
    form_dict["raw_form_json"] = req.metadata.model_dump(mode="json")
    
    valid_cols = {c.name for c in DatasetMetadata.__table__.columns}
    insert_dict = {k: v for k, v in form_dict.items() if k in valid_cols}
    
    new_metadata = DatasetMetadata(**insert_dict)
    db.add(new_metadata)

    await db.commit()
    
    await audit_logger.log_event(
        db,
        assessment_id,
        "assessment_submitted",
        {"file_key": req.file_key, "dataset_id": dataset_id},
        "api"
    )

    run_assessment.delay(str(assessment_id), req.file_key, req.metadata.model_dump(mode="json"))

    return AssessmentSubmitResponse(
        assessment_id=assessment_id,
        status="queued",
        estimated_completion_seconds=180,
        poll_url=f"/api/v1/assess/{assessment_id}",
        submission_timestamp=new_assessment.submission_timestamp,
        submitted_at=new_assessment.submission_timestamp
    )

@router.get(
    "/",
    response_model=List[AssessmentStatusResponse],
)
async def list_user_assessments(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Returns a paginated list of the current user's assessments."""
    stmt = select(Assessment).where(Assessment.user_id == current_user.id).order_by(desc(Assessment.submission_timestamp)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    assessments = result.scalars().all()
    
    return [
        AssessmentStatusResponse(
            assessment_id=a.assessment_id,
            status=a.status,
            dataset_id=a.dataset_id,
            submission_timestamp=a.submission_timestamp,
            completion_timestamp=a.completion_timestamp,
            error_message=a.error_message
        ) for a in assessments
    ]


@router.get(
    "/{assessment_id}",
    response_model=Union[AssessmentResultResponse, AssessmentStatusResponse],
    responses={
        401: {"description": "Not authenticated or invalid token"},
        403: {"description": "Access denied / Admin isolation / Not owner"},
        404: {"description": "Assessment not found"}
    }
)
async def get_assessment_status_route(
    assessment: Assessment = Depends(get_user_assessment)
):
    """Checks the status of an active or completed assessment, verifying ownership limits."""
    return AssessmentStatusResponse(
        assessment_id=assessment.assessment_id,
        status=assessment.status,
        dataset_id=assessment.dataset_id,
        submission_timestamp=assessment.submission_timestamp,
        completion_timestamp=assessment.completion_timestamp,
        error_message=assessment.error_message
    )
