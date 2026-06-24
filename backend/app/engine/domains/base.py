from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class DomainScoreResult(BaseModel):
    domain_number: int
    domain_name: str
    score: Optional[int]
    rationale: str
    evidence_items: List[str]
    gaps: List[str]
    confidence: str
    not_applicable: bool = False

class BaseDomainScorer(ABC):
    def __init__(self, profile: Dict[str, Any], metadata: Dict[str, Any], criteria: Dict[str, Any]):
        self.profile = profile
        self.metadata = metadata
        self.criteria = criteria

    @abstractmethod
    def score(self) -> DomainScoreResult:
        """Computes the 0-4 score. Must be overridden by subclasses."""
        pass
