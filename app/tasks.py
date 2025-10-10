import requests
from sqlalchemy.orm import Session
from . import schemas, crud, database
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from .config import settings
from .scrapeNews import get_article_text, clean_text_paragraphs

# Example external API (replace with your own)
NEWS_API_URL = settings.GNEWS_SEARCH_API_URL
API_KEY = settings.GNEWS_API_KEY

def fetch_and_store_news():
    db: Session = next(database.get_db())  # Get DB session
    
    to_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    from_time = to_time - timedelta(days=1)

    to_str = to_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    from_str = from_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    try:
        params = {
            "apikey": API_KEY,
            "lang": "en",
            "country": "in",
            "from": from_str,
            "to": to_str,
            "q": "indian stock market OR sensex OR nifty OR NSE OR BSE OR equities OR shares OR trading OR IPO OR results OR earnings",
            "sortby": "publishedAt"
        }

        print("Parameters: ", params)
        response = requests.get(NEWS_API_URL, params=params)
        print("Response: ", response.json())
        data = response.json()

        articles = data.get("articles", [])
        print("Articles: ", articles)
        count = 0
        for article in articles:
            news_item = schemas.NewsCreate(
                title=article.get("title"),
                description=article.get("description"),
                url=article.get("url"),
                content=clean_text_paragraphs(article.get("content")),
                source=article.get("source", {}).get("name", "Unknown"),
                image=article.get("image"),
                published_at=article.get("publishedAt"),
                gnews_id=article.get("id"),
                api_source="gnews",
                full_content=get_article_text(article.get("url"))
            )
            # avoid duplicate entries
            existing = crud.get_news_by_gnews_id(db, gnews_id=news_item.gnews_id)
            if not existing:
                crud.create_news(db, news_item)
                print(f"✅ Stored news article: {news_item.gnews_id}")
                count += 1
            else:
                print(f"❌ Skipping duplicate entry: {news_item.gnews_id}")

        print(f"✅ Stored {count} news articles")

    except Exception as e:
        print(f"❌ Error fetching and storing news: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fetch_and_store_news()