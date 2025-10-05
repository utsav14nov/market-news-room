from sqlalchemy.orm import Session
from . import models, schemas

def create_news(db: Session, news: schemas.NewsCreate):
    db_news = models.News(**news.dict())
    db.add(db_news)
    db.commit()
    db.refresh(db_news)
    return db_news

def get_news(db: Session, skip: int = 0, limit: int = 20):
    return db.query(models.News).order_by(models.News.published_at.desc()).offset(skip).limit(limit).all()

def get_news_by_gnews_id(db: Session, gnews_id: str):
    return db.query(models.News).filter(models.News.gnews_id == gnews_id).first()
