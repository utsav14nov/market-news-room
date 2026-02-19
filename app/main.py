from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

from app.routes import news_router

app = FastAPI(
    title="Market News Room API",
    description="Stock market news with AI-generated visuals",
    version="1.0.0",
)

app.include_router(news_router)

# Serve generated news images if the directory exists
news_images_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "news_images")
if os.path.isdir(news_images_path):
    app.mount("/news_images", StaticFiles(directory=news_images_path), name="news_images")


@app.get("/health")
def health():
    return {"status": "ok"}
