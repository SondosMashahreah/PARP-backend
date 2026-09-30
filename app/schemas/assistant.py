from pydantic import BaseModel, Field


class AssistantMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AssistantMessageResponse(BaseModel):
    answer: str
