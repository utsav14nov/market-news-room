from sqlalchemy import Column, Integer, String, Text, DateTime, func
from .database import Base

class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    image = Column(String(500), nullable=True)
    published_at = Column(DateTime, nullable=True)
    gnews_id = Column(String(255), unique=True, nullable=False)
    url = Column(String(500), unique=True, nullable=False)
    content = Column(Text, nullable=True)
    source = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    api_source = Column(String(100), nullable=True)
