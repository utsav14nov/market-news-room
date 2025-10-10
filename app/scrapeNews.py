import trafilatura
# from newspaper import Article
from playwright.sync_api import sync_playwright
import re

def clean_text_paragraphs(text: str) -> str:
    if not text:
        return ""
    # Normalize line endings
    text = text.replace('\r\n', '\n')
    # Split by 2+ newlines into paragraphs
    paragraphs = [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\n{2,}', text)]
    # Remove empty ones
    paragraphs = [p for p in paragraphs if p]
    # Join with single newlines
    return "\n\n".join(paragraphs)

def fetch_full_article(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()
    text = trafilatura.extract(html)
    return text


def get_article_text(url):
    # try trafilatura first
    html = trafilatura.fetch_url(url)
    text = trafilatura.extract(html)
    if text and len(text) > 100:
        return clean_text_paragraphs(text)

    # fallback to Playwright
    return clean_text_paragraphs(fetch_full_article(url))