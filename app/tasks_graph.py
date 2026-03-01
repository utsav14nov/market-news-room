"""LangGraph-based news ingestion pipeline.

Graph topology (cycles allowed — LangGraph supports them):

  START
    │
    ▼
  fetch_articles          ← hits GNews API, returns article list
    │
    ▼
  select_next_article  ◄──────────────────────────────────┐
    │                                                      │
    ├─ (stop: no more articles OR processed_count ≥ 5) ──► END
    │                                                      │
    ▼ (continue)                                           │
  crawl_content           ← trafilatura / Playwright       │
    │                                                      │
    ▼                                                      │
  check_duplicate         ← DB lookup                     │
    │                                                      │
    ├─ (duplicate) ────────────────────────────────────────┘
    │                                                      │
    ▼ (new)                                                │
  summarize_bullets       ← Gemini text: full → bullets   │
    │                                                      │
    ▼                                                      │
  analyze_sentiment       ← Gemini: sentiment JSON        │
    │                                                      │
    ▼                                                      │
  generate_image          ← Gemini image: bullets → PNG   │
    │                                                      │
    ▼                                                      │
  store_news              ← write to DB ──────────────────┘
"""

from __future__ import annotations

from typing import TypedDict, Optional
import json

import requests
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from langgraph.graph import StateGraph, END, START

from . import schemas, crud, database
from .config import settings
from .scrapeNews import get_article_text, clean_text_paragraphs
from .google_gemini import GoogleGemini

NEWS_API_URL = settings.GNEWS_SEARCH_API_URL
API_KEY = settings.GNEWS_API_KEY
MAX_NEW_ARTICLES = 5


# ---------------------------------------------------------------------------
# Shared state flowing through every node
# ---------------------------------------------------------------------------

class NewsWorkflowState(TypedDict):
    # ── populated by fetch_articles ──────────────────────────────────────
    articles: list[dict]
    current_index: int
    processed_count: int

    # ── populated / reset by select_next_article ─────────────────────────
    current_article: Optional[dict]   # None  →  no more articles

    # ── per-article pipeline state ────────────────────────────────────────
    full_content: Optional[str]
    is_duplicate: bool
    bullet_points: Optional[str]
    sentiment_result: Optional[dict]
    generated_image: Optional[str]        # first image URL (backward compat)
    generated_images: Optional[list]      # all image URLs


# ---------------------------------------------------------------------------
# Workflow class — holds DB session + Gemini client + compiled graph
# ---------------------------------------------------------------------------

class NewsWorkflow:

    def __init__(self) -> None:
        self.db: Session = next(database.get_db())
        self.gemini = GoogleGemini()
        self.seen_abbreviations: set = set()  # dedup across articles in this run
        self.app = self._build_graph()

    # ------------------------------------------------------------------ nodes

    def fetch_articles(self, state: NewsWorkflowState) -> dict:
        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(hours=24)

        params = {
            "apikey": API_KEY,
            "lang": "en",
            "country": "in",
            "from": from_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "to": to_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "q": (
                "indian stock market OR sensex OR nifty OR NSE OR BSE "
                "OR equities OR shares OR trading OR IPO OR results OR earnings"
            ),
            "sortby": "publishedAt",
            "pageSize": 10,
        }

        try:
            response = requests.get(NEWS_API_URL, params=params, timeout=30)
            articles = response.json().get("articles", [])
        except Exception as e:
            print(f"❌ Error fetching articles: {e}")
            articles = []

        print(f"Fetched {len(articles)} articles from GNews")
        return {"articles": articles, "current_index": 0, "processed_count": 0}

    def select_next_article(self, state: NewsWorkflowState) -> dict:
        """Pick the next article from the list and reset per-article state."""
        idx = state.get("current_index", 0)
        articles = state.get("articles", [])

        if idx < len(articles):
            raw = articles[idx]
            article = {
                "title": raw.get("title"),
                "description": raw.get("description"),
                "url": raw.get("url"),
                "content": clean_text_paragraphs(raw.get("content") or ""),
                "source": (raw.get("source") or {}).get("name", "Unknown"),
                "original_image": raw.get("image"),
                "published_at": raw.get("publishedAt"),
                "gnews_id": raw.get("id"),
                "api_source": "gnews",
            }
            print(
                f"[{idx + 1}/{len(articles)}] Selecting article: "
                f"{article.get('gnews_id')}"
            )
        else:
            article = None

        return {
            "current_article": article,
            "current_index": idx + 1,
            # reset per-article fields
            "full_content": None,
            "bullet_points": None,
            "sentiment_result": None,
            "generated_image": None,
            "generated_images": None,
            "is_duplicate": False,
        }

    def crawl_content(self, state: NewsWorkflowState) -> dict:
        url = state["current_article"]["url"]
        try:
            full_content = get_article_text(url) or ""
        except Exception as e:
            print(f"  ❌ Crawl error for {url}: {e}")
            full_content = ""

        print(
            f"  Crawled {len(full_content)} chars "
            f"({state['current_article'].get('gnews_id')})"
        )
        return {"full_content": full_content}

    def check_duplicate(self, state: NewsWorkflowState) -> dict:
        gnews_id = state["current_article"]["gnews_id"]
        existing = crud.get_news_by_gnews_id(self.db, gnews_id=gnews_id)
        is_dup = existing is not None
        if is_dup:
            print(f"  ❌ Duplicate – skipping {gnews_id}")
        return {"is_duplicate": is_dup}

    def summarize_bullets(self, state: NewsWorkflowState) -> dict:
        """
        Convert full article text into 5-8 clean bullet points.
        These bullets become the sole input to the image generator, giving the
        model focused, non-overlapping facts instead of dense prose.
        They are also persisted to the DB for display / debugging.
        """
        gnews_id = state["current_article"]["gnews_id"]
        full_content = state.get("full_content") or ""
        bullets = self.gemini.summarize_to_bullets(full_content, gnews_id)
        print(f"  Bullet points for {gnews_id}:\n{bullets}")
        return {"bullet_points": bullets}

    def analyze_sentiment(self, state: NewsWorkflowState) -> dict:
        gnews_id = state["current_article"]["gnews_id"]
        full_content = state.get("full_content") or ""
        sentiment = self.gemini.analyze_sentiment(full_content, gnews_id)
        print(f"  Sentiment for {gnews_id}: {sentiment}")
        return {"sentiment_result": sentiment}

    def generate_image(self, state: NewsWorkflowState) -> dict:
        gnews_id = state["current_article"]["gnews_id"]
        source = state.get("bullet_points") or state.get("full_content") or ""
        image_urls = self.gemini.generate_images_for_article(source, gnews_id)
        return {
            "generated_image": image_urls[0] if image_urls else None,
            "generated_images": image_urls,
        }

    def store_news(self, state: NewsWorkflowState) -> dict:
        article = state["current_article"]
        sentiment = state.get("sentiment_result") or {}

        news_item = schemas.NewsCreate(
            title=article["title"],
            description=article.get("description") or "",
            url=article["url"],
            content=article.get("content") or "",
            source=article.get("source") or "Unknown",
            original_image=article.get("original_image"),
            published_at=article.get("published_at"),
            gnews_id=article["gnews_id"],
            api_source="gnews",
            full_content=state.get("full_content") or "",
            bullet_points=state.get("bullet_points"),
            sentiment_verdict=sentiment.get("sentiment"),
            sentiment_score=sentiment.get("score"),
            sentiment_confidence=sentiment.get("confidence"),
            generated_image=state.get("generated_image"),
            generated_images=json.dumps(state.get("generated_images") or []),
        )

        crud.create_news(self.db, news_item)
        new_count = state.get("processed_count", 0) + 1
        print(
            f"  ✅ Stored {article['gnews_id']} "
            f"({new_count}/{MAX_NEW_ARTICLES})"
        )
        return {"processed_count": new_count}

    # ---------------------------------------------------- conditional routers

    def should_continue(self, state: NewsWorkflowState) -> str:
        """Decide whether to process the next article or stop."""
        if state.get("current_article") is None:
            return "stop"
        if state.get("processed_count", 0) >= MAX_NEW_ARTICLES:
            return "stop"
        return "continue"

    def is_new_or_duplicate(self, state: NewsWorkflowState) -> str:
        return "duplicate" if state.get("is_duplicate") else "new"

    # ------------------------------------------------------------------ graph

    def _build_graph(self):
        wf = StateGraph(NewsWorkflowState)

        # nodes
        wf.add_node("fetch_articles",      self.fetch_articles)
        wf.add_node("select_next_article", self.select_next_article)
        wf.add_node("crawl_content",       self.crawl_content)
        wf.add_node("check_duplicate",     self.check_duplicate)
        wf.add_node("summarize_bullets",   self.summarize_bullets)
        wf.add_node("analyze_sentiment",   self.analyze_sentiment)
        wf.add_node("generate_image",      self.generate_image)
        wf.add_node("store_news",          self.store_news)

        # linear start
        wf.add_edge(START, "fetch_articles")
        wf.add_edge("fetch_articles", "select_next_article")

        # gate: keep going or finish?
        wf.add_conditional_edges(
            "select_next_article",
            self.should_continue,
            {"continue": "crawl_content", "stop": END},
        )

        wf.add_edge("crawl_content", "check_duplicate")

        # gate: skip duplicate or process new article?
        wf.add_conditional_edges(
            "check_duplicate",
            self.is_new_or_duplicate,
            {
                "duplicate": "select_next_article",  # loop back, skip
                "new":       "summarize_bullets",    # summarise first
            },
        )

        # linear processing chain for new articles
        wf.add_edge("summarize_bullets", "analyze_sentiment")
        wf.add_edge("analyze_sentiment", "generate_image")
        wf.add_edge("generate_image",    "store_news")
        wf.add_edge("store_news",        "select_next_article")  # loop back

        return wf.compile()

    # ------------------------------------------------------------------ entry

    def run(self) -> None:
        try:
            final_state = self.app.invoke(
                {
                    "articles": [],
                    "current_index": 0,
                    "processed_count": 0,
                    "current_article": None,
                    "full_content": None,
                    "is_duplicate": False,
                    "bullet_points": None,
                    "sentiment_result": None,
                    "generated_image": None,
                    "generated_images": None,
                },
                config={"recursion_limit": 200},
            )
            print(
                f"\n✅ Workflow complete. "
                f"Stored {final_state.get('processed_count', 0)} articles."
            )
        except Exception as e:
            print(f"❌ Workflow error: {e}")
            raise
        finally:
            self.db.close()


# ---------------------------------------------------------------------------
# Public entry point — drop-in replacement for tasks.fetch_and_store_news
# ---------------------------------------------------------------------------

def fetch_and_store_news() -> None:
    NewsWorkflow().run()


if __name__ == "__main__":
    fetch_and_store_news()
