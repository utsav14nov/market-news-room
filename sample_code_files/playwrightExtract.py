from playwright.sync_api import sync_playwright
import trafilatura

def fetch_full_article(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()
    text = trafilatura.extract(html)
    return text

url = "https://www.lokmattimes.com/business/sensex-rises-583-points-nifty-tops-25000-as-it-banking-stocks-lead-rally/"
article_text = fetch_full_article(url)

print(article_text if article_text else "❌ Could not extract text")
