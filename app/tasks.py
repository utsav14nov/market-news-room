import requests
from sqlalchemy.orm import Session
from . import schemas, crud, database
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from .config import settings
from .scrapeNews import get_article_text, clean_text_paragraphs
from .google_gemini import GoogleGemini

# Example external API (replace with your own)
NEWS_API_URL = settings.GNEWS_SEARCH_API_URL
API_KEY = settings.GNEWS_API_KEY

def fetch_and_store_news():
    db: Session = next(database.get_db())  # Get DB session

    gemini = GoogleGemini()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(hours=24)

    to_str = to_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    from_str = from_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    print(f"Fetching for {from_time} to {to_time}")

    try:
        params = {
            "apikey": API_KEY,
            "lang": "en",
            "country": "in",
            "from": from_str,
            "to": to_str,
            "q": "indian stock market OR sensex OR nifty OR NSE OR BSE OR equities OR shares OR trading OR IPO OR results OR earnings",
            "sortby": "publishedAt",
            "pageSize": 10
        }


        response = requests.get(NEWS_API_URL, params=params)
        data = response.json()

        articles = data.get("articles", [])
        print(f"Found {len(articles)} articles")
        count = 0
        for article in articles:
            news_item = schemas.NewsCreate(
                title=article.get("title"),
                description=article.get("description"),
                url=article.get("url"),
                content=clean_text_paragraphs(article.get("content")),
                source=article.get("source", {}).get("name", "Unknown"),
                original_image=article.get("image"),
                published_at=article.get("publishedAt"),
                gnews_id=article.get("id"),
                api_source="gnews",
                full_content=get_article_text(article.get("url"))
            )
            # avoid duplicate entries
            existing = crud.get_news_by_gnews_id(db, gnews_id=news_item.gnews_id)
            if not existing:
                sentiment = gemini.analyze_sentiment(news_item.full_content, news_item.gnews_id)
                print(f"Sentiment for {news_item.gnews_id}: {sentiment}")
                news_item.sentiment_verdict = sentiment.get("sentiment")
                news_item.sentiment_score = sentiment.get("score")
                news_item.sentiment_confidence = sentiment.get("confidence")
                image = gemini.generate_nano_banana_image(news_item.full_content, news_item.gnews_id)
                news_item.generated_image = image
                crud.create_news(db, news_item)
                print(f"✅ Stored news article: {news_item.gnews_id}")
                count += 1
            else:
                print(f"❌ Skipping duplicate entry: {news_item.gnews_id}")
            
            if count >= 5:
                break

        print(f"✅ Stored {count} news articles")

    except Exception as e:
        print(f"❌ Error fetching and storing news: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fetch_and_store_news()