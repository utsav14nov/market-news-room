# market-news-room
Stock market news application having AI generated visuals.

## REST API

Run the API server:

```bash
uvicorn app.main:app --reload
```

- **Docs:** http://127.0.0.1:8000/docs  
- **ReDoc:** http://127.0.0.1:8000/redoc  

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/news` | List news (query: `skip`, `limit`) |
| GET | `/news/{id}` | Get article by internal id |
| GET | `/news/by-gnews-id/{gnews_id}` | Get article by GNews id |
| POST | `/news` | Create article (body: `NewsCreate`) |
| GET | `/news_images/{filename}` | Generated image file |
