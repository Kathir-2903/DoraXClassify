from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.utils.validators import normalize_email, normalize_phone

LEAD_SOURCES = ["Website", "Referral", "Webinar", "Social Media", "Google Ads", "Event", "Cold Outreach", "Partner", "Other"]
LeadStatusT = Literal["new", "meeting_scheduled", "engaged", "follow_up", "no_show", "won", "lost"]


class LeadBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120, examples=["Rahul Kumar"])
    email: str = Field(..., examples=["rahul@example.com"])
    phone: str = Field(..., examples=["+919876543210"])
    company: Optional[str] = Field(None, max_length=160)
    lead_source: Optional[str] = Field(None, max_length=60, examples=["Website"])
    interested_product: Optional[str] = Field(None, max_length=160, examples=["Full Stack Development"])
    notes: Optional[str] = Field(None, max_length=4000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)


class LeadCreate(LeadBase):
    sales_person_id: Optional[str] = Field(None, description="Admins may assign; sales users are always assigned to themselves")


class LeadUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = Field(None, max_length=160)
    lead_source: Optional[str] = Field(None, max_length=60)
    interested_product: Optional[str] = Field(None, max_length=160)
    notes: Optional[str] = Field(None, max_length=4000)
    sales_person_id: Optional[str] = None
    lead_status: Optional[LeadStatusT] = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        return normalize_email(v) if v else v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v) if v else v


class LeadListResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int
