"""Request models for AI analysis."""
from typing import Optional

from pydantic import BaseModel, Field


class ReanalyzeRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=300)
