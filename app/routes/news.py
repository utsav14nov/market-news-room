from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=list[schemas.NewsResponse])
def list_news(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """List news articles with pagination (ordered by published_at desc)."""
    print(f"Listing news articles with skip: {skip} and limit: {limit}")
    return crud.get_news(db, skip=skip, limit=limit)


@router.get("/by-gnews-id/{gnews_id}", response_model=schemas.NewsResponse)
def get_news_by_gnews_id(
    gnews_id: str,
    db: Session = Depends(get_db),
):
    """Get a single news article by GNews id."""
    news = crud.get_news_by_gnews_id(db, gnews_id=gnews_id)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    return news


@router.get("/{news_id}", response_model=schemas.NewsResponse)
def get_news_by_id(
    news_id: int,
    db: Session = Depends(get_db),
):
    """Get a single news article by internal id."""
    news = crud.get_news_by_id(db, news_id=news_id)
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    return news


@router.post("", response_model=schemas.NewsResponse, status_code=201)
def create_news(
    payload: schemas.NewsCreate,
    db: Session = Depends(get_db),
):
    """Create a news article (e.g. for manual ingest)."""
    existing = crud.get_news_by_gnews_id(db, gnews_id=payload.gnews_id)
    if existing:
        raise HTTPException(status_code=409, detail="News with this gnews_id already exists")
    return crud.create_news(db, payload)
