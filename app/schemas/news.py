from pydantic import BaseModel, ConfigDict, Field

class NewsWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    title: str = Field(min_length=1, max_length=300)
    title_en: str = Field(default='', max_length=300)
    excerpt: str = Field(default='', max_length=1000)
    excerpt_en: str = Field(default='', max_length=1000)
    body: str = Field(min_length=1, max_length=100000)
    body_en: str = Field(default='', max_length=100000)
    category: str = Field(default='أخبار المنصة', min_length=1, max_length=100)
    category_en: str = Field(default='', max_length=100)
    image_alt: str = Field(default='', max_length=300)
    published: bool = False
