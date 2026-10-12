from typing import Literal
from pydantic import BaseModel, Field, model_validator


class DraftContent(BaseModel):
    kind: Literal["research", "practice"] = "research"
    title: str = Field(default='', max_length=500)
    research_field: str = Field(default='', max_length=150)
    problem: str = Field(default='', max_length=12000)
    abstract: str = Field(default='', max_length=12000)
    research_question: str = Field(default='', max_length=12000)
    intervention: str = Field(default='', max_length=12000)
    results: str = Field(default='', max_length=12000)
    recommendations: str = Field(default='', max_length=12000)
    keywords: str = Field(default='', max_length=2000)


class DraftSave(BaseModel):
    content: DraftContent
    revision: int = Field(ge=1)


class ProgressSave(BaseModel):
    course_key: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=250)
    completed: int = Field(ge=0)
    total: int = Field(ge=1)

    @model_validator(mode='after')
    def validate_progress(self):
        if self.completed > self.total:
            raise ValueError('Completed units cannot exceed total units')
        return self
