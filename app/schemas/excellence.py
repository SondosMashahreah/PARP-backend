from pydantic import BaseModel, ConfigDict, Field

class ExcellenceWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    conference_id: int = Field(gt=0)
    submission_id: int = Field(gt=0)
    name_ar: str = Field(min_length=2, max_length=150)
    name_en: str = Field(min_length=2, max_length=150)
    conference_title_en: str = Field(default='', max_length=300)
    visible: bool = False
    sort_order: int = Field(default=0, ge=0, le=10000)
