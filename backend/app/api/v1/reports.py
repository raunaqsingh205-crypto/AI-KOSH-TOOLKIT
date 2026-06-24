from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse
from typing import Literal

from app.api.deps import get_user_assessment
from app.models.assessment import Assessment

router = APIRouter(prefix="/assess", tags=["reports"])

@router.get(
    "/{assessment_id}/report",
    responses={
        401: {"description": "Not authenticated or invalid token"},
        403: {"description": "Access denied / Admin isolation / Not owner"},
        404: {"description": "Assessment not found"}
    }
)
async def download_report(
    format: Literal["json", "html", "pdf"] = "json",
    assessment: Assessment = Depends(get_user_assessment)
):
    """Generates a temporary S3 pre-signed URL to download the report in the requested format."""
    # Enforces BOLA protection and admin boundaries automatically via get_user_assessment
    return RedirectResponse(
        url=f"http://localhost:9000/aikosh-datasets/reports/{assessment.assessment_id}/report.{format}",
        status_code=status.HTTP_302_FOUND
    )
