from typing import Dict, Any, Literal
from pydantic import BaseModel

class ReleaseClassificationResult(BaseModel):
    classification: Literal["Open", "Controlled", "Restricted"]
    justification: str
    policy_override_applied: bool

class ReleaseClassificationEngine:
    @staticmethod
    def classify_release(cqi: float, prs: int, sensitivity_class: str) -> ReleaseClassificationResult:
        """Applies the CQI x PRS matrix to classify the dataset release."""
        # Simple placeholder implementation complying with release matrix rules
        prs_band = "Low" if prs <= 15 else "Moderate" if prs <= 40 else "High" if prs <= 70 else "Very High"
        
        if sensitivity_class in ["high_stigma", "critical"]:
            if prs_band != "Low":
                return ReleaseClassificationResult(
                    classification="Restricted",
                    justification="High sensitivity classification and non-low PRS forces Restricted status.",
                    policy_override_applied=True
                )
            return ReleaseClassificationResult(
                classification="Controlled",
                justification="High sensitivity classification defaults to Controlled access.",
                policy_override_applied=True
            )
            
        if cqi >= 70 and prs_band == "Low":
            return ReleaseClassificationResult(classification="Open", justification="High CQI and Low PRS.", policy_override_applied=False)
            
        return ReleaseClassificationResult(classification="Controlled", justification="Standard classification.", policy_override_applied=False)
