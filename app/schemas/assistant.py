from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class HistoryMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=12000)

class AssistantMessageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: str = Field(min_length=1, max_length=16000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=8)
    mode: Literal['platform', 'write', 'evaluate'] = 'platform'
    allow_external: bool = False

class AssistantSource(BaseModel):
    id: str
    label: str
    url: str
    kind: Literal['platform', 'external'] = 'platform'

class AssistantMessageResponse(BaseModel):
    answer: str
    sources: list[AssistantSource] = Field(default_factory=list)
    generated_at: str
    scope: str

class ReadRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset: Literal['summary','news','research','people','schools','excellence','conferences','participations','drafts','training','certificates','payments','notices','problems','recommendations','affiliations','assignments','knowledge']
    q: str = Field(default='', max_length=150)
    record_id: str | None = Field(default=None, max_length=80)
    author_id: int | None = Field(default=None, ge=1)
    status: str | None = Field(default=None, max_length=40)
    kind: Literal['research','practice'] | None = None
    offset: int = Field(default=0, ge=0, le=100000)
    visibility: Literal['public','workspace'] = 'public'
