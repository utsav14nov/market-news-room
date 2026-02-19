import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    GNEWS_SEARCH_API_URL: str = os.getenv("GNEWS_SEARCH_API_URL")
    GNEWS_API_KEY: str = os.getenv("GNEWS_API_KEY")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    GEMINI_BUCKET_NAME: str = os.getenv("GEMINI_BUCKET_NAME")

settings = Settings()