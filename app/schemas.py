from pydantic import BaseModel
from datetime import datetime

class NewsBase(BaseModel):
    title: str
    url: str
    content: str
    source: str

class NewsCreate(NewsBase):
    description: str
    image: str
    published_at: str
    gnews_id: str
    source: str
    content: str
    title: str
    url: str
    api_source: str

class NewsResponse(NewsBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
