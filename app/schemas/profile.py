from pydantic import BaseModel, Field


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    full_name_en: str | None = Field(default=None, min_length=2, max_length=150)
