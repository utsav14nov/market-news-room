from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class NewsBase(BaseModel):
    title: str
    url: str
    content: str
    source: str

class NewsCreate(NewsBase):
    description: str
    published_at: str
    gnews_id: str
    original_image: Optional[str] = None
    source: str
    content: str
    title: str
    url: str
    api_source: str
    full_content: str
    sentiment_verdict: Optional[str] = None
    sentiment_score: Optional[float] = None
    sentiment_confidence: Optional[float] = None
    generated_image: Optional[str] = None
    generated_images: Optional[str] = None  # JSON-encoded list of image URLs
    bullet_points: Optional[str] = None

class NewsResponse(NewsBase):
    id: int
    description: Optional[str] = None
    original_image: Optional[str] = None
    # Match the SQLAlchemy model's DateTime column
    published_at: Optional[datetime] = None
    gnews_id: str
    full_content: Optional[str] = None
    api_source: Optional[str] = None
    sentiment_verdict: Optional[str] = None
    sentiment_score: Optional[float] = None
    sentiment_confidence: Optional[float] = None
    generated_image: Optional[str] = None
    generated_images: Optional[str] = None  # JSON-encoded list of image URLs
    bullet_points: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True  # orm_mode in Pydantic v1
