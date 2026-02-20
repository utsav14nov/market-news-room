from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.routes import news_router

app = FastAPI(
    title="Market News Room API",
    description="Stock market news with AI-generated visuals",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173","http://34.57.136.20","http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to React build (app/react-build)
react_build_path = os.path.join(os.path.dirname(__file__), "react-build")

app.include_router(news_router)

# Serve generated news images if the directory exists
news_images_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "news_images")
if os.path.isdir(news_images_path):
    app.mount("/news_images", StaticFiles(directory=news_images_path), name="news_images")


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve React SPA - must be last so /news, /health etc. are matched first
if os.path.isdir(react_build_path):
    assets_path = os.path.join(react_build_path, "assets")
    if os.path.isdir(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        static_file = os.path.join(react_build_path, full_path)
        if os.path.isfile(static_file):
            return FileResponse(static_file)
        return FileResponse(os.path.join(react_build_path, "index.html"))
