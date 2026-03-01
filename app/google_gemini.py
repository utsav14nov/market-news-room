from __future__ import annotations

from typing import Optional
from .config import settings
from google import genai
import json
import os
from PIL import Image
from google.cloud import storage

# Max KEY INSIGHTS per image — if an article has more, extra images are generated
INSIGHTS_PER_IMAGE = 8


class GoogleGemini:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.client = genai.Client(api_key=self.api_key)

    def parse_response(self, response_text):
        try:
            if not response_text:
                raise ValueError("Empty response from Gemini")

            text = response_text.strip()

            # If the model wrapped JSON in markdown code fences, strip them
            if text.startswith("```"):
                lines = [
                    line for line in text.splitlines()
                    if not line.strip().startswith("```")
                ]
                text = "\n".join(lines).strip()

            # If there's extra text around the JSON, try to isolate the JSON object
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and start < end:
                text = text[start:end + 1]

            return json.loads(text)
        except Exception as e:
            print(f"Error parsing response: {e} | raw: {response_text}")
            return {
                "sentiment": "unknown",
                "score": 0.0,
                "confidence": 0.0
            }

    def upload_blob(self, source_file_name, destination_blob_name):
        storage_client = storage.Client()
        bucket = storage_client.bucket(settings.GEMINI_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)

        # No generation precondition — always overwrite if the file already exists
        blob.upload_from_filename(source_file_name)

        print(
            f"File {source_file_name} uploaded to {destination_blob_name}."
        )

    def analyze_sentiment(self, news_text: str, gnews_id: str):
        print(f"Analyzing sentiment for {gnews_id}")
        prompt = f"""
        Analyze the sentiment of the following Indian market news.

        Respond strictly in JSON with:
        - sentiment: Positive | Neutral | Negative
        - score: number between -1 and +1
        - confidence: number between 0 and 1

        News:
        {news_text}
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[prompt]
            )
            print(f"Response from Gemini for {gnews_id}: {response.text}")
        except Exception as e:
            print(f"Error from Gemini for {gnews_id}: {e}")
            return {
                "sentiment": "unknown",
                "score": 0.0,
                "confidence": 0.0
            }

        return self.parse_response(response.text)

    def summarize_to_bullets(self, news_text: str, gnews_id: str) -> str:
        """
        Summarise full article into two structured sections for image generation:
          KEY INSIGHTS  — rich, descriptive bullets with facts, context, and impact
          ABBREVIATIONS — professional/technical terms only, with full forms
        """
        print(f"Summarising to bullets for {gnews_id}")
        prompt = f"""
        You are a financial news analyst specialising in Indian equity markets.

        Read the news article below and produce a structured summary in EXACTLY TWO SECTIONS.

        ═══════════════════════════════════════
        SECTION 1 — KEY INSIGHTS
        ═══════════════════════════════════════
        Rules:
        - 6 to 10 bullets, each prefixed with "•"
        - Each bullet must cover: main fact + magnitude/number + cause or context + impact or implication
          (include only the parts that are explicitly stated in the article — do NOT infer)
        - Max ~30 words per bullet — be thorough and descriptive, not vague
        - Include specific numbers, % changes, index levels, company names, dates, and rupee/dollar amounts
        - Use ONLY facts explicitly stated in the article — never infer, calculate, or guess
        - Write full names first then abbreviation in parentheses on first use: e.g. "Foreign Institutional Investors (FIIs)"

        Good example (descriptive, fact-rich):
        • Sensex tumbled 961 pts (1.17%) to close at 81,287 on Feb 27, dragged by Iran-Israel tensions that spiked Brent crude 3%, threatening India's oil import bill.
        • India meets 85–90% of its crude demand via imports; a $10/barrel crude rise adds ₹10,000–15,000 crore to the annual import bill.

        ═══════════════════════════════════════
        SECTION 2 — ABBREVIATIONS USED
        ═══════════════════════════════════════
        Rules:
        - List ONLY highly technical / niche financial abbreviations used in Section 1
        - Only include terms that even a regular stock market follower would need explained
        - INCLUDE: SEBI, DRHP, OFS, QIP, F&O, STT, FII, DII, FPI, WTI, bpd, bbl,
          EBITDA, EPS, NAV, EMA, RSI, MACD, P/E, PCR, VIX (as fear index context only if unclear)
        - DO NOT include ANY of the following — they are common knowledge for Indian market readers:
          NSE, BSE, IPO, FY, GDP, RBI, Sensex, Nifty, USD, INR, %, pts, Cr, lakh, bn,
          Q1/Q2/Q3/Q4, IT, AI, MNC, CEO, MD, CFO, or any plain English word
        - Format: TERM = Full Form  (max 5 words — no dash explanation)
        - Prefix each entry with "•"
        - If no qualifying abbreviations appear in Section 1, write exactly: ABBREVIATIONS:\n(none)

        ═══════════════════════════════════════
        OUTPUT FORMAT — STRICT
        ═══════════════════════════════════════
        Return ONLY this exact structure — no titles, no intro, no trailing commentary:

        KEY INSIGHTS:
        • [insight 1]
        • [insight 2]
        ...

        ABBREVIATIONS:
        • [TERM] = [Full Form]
        ...

        NEWS ARTICLE:
        {news_text}
        """
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt]
            )
            return response.text.strip()
        except Exception as e:
            print(f"Error summarising for {gnews_id}: {e}")
            return news_text  # fallback to raw content

    # ------------------------------------------------------------------
    # Helpers for multi-image generation
    # ------------------------------------------------------------------

    def _parse_bullet_sections(self, bullet_points: str) -> tuple[list[str], list[str]]:
        """
        Parse the two-section bullet_points string into separate lists.
        Returns (insights, abbreviations) where each entry is a '•' prefixed string.
        """
        insights: list[str] = []
        abbreviations: list[str] = []
        current_section = None

        for line in bullet_points.strip().splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("KEY INSIGHTS:"):
                current_section = "insights"
            elif stripped.startswith("ABBREVIATIONS:"):
                current_section = "abbreviations"
            elif stripped.startswith("•"):
                clean = stripped.lstrip("•").strip()
                if clean in ("(none)", ""):
                    continue
                if current_section == "insights":
                    insights.append(stripped)
                elif current_section == "abbreviations":
                    abbreviations.append(stripped)

        return insights, abbreviations

    def generate_images_for_article(self, bullet_points: str, gnews_id: str) -> list[str]:
        """
        Generate one or more images for an article.

        - If KEY INSIGHTS count <= INSIGHTS_PER_IMAGE  → single image (gnews_id.png)
        - If KEY INSIGHTS count  > INSIGHTS_PER_IMAGE  → split into chunks;
          first image is gnews_id.png, subsequent are gnews_id_2.png, gnews_id_3.png …
        - All abbreviations are included in every image chunk.
        Returns a list of GCS URLs (empty if all generations fail).
        """
        insights, abbreviations = self._parse_bullet_sections(bullet_points)

        if not insights:
            # Fallback: pass raw bullet_points as-is to a single image
            print(f"  No parsed insights for {gnews_id} — falling back to raw prompt")
            url = self._generate_single_image(bullet_points, gnews_id)
            return [url] if url else []

        # Split insights into chunks
        chunks = [
            insights[i: i + INSIGHTS_PER_IMAGE]
            for i in range(0, len(insights), INSIGHTS_PER_IMAGE)
        ]

        abbrev_block = (
            "ABBREVIATIONS:\n" + "\n".join(abbreviations)
            if abbreviations
            else "ABBREVIATIONS:\n(none)"
        )

        total = len(chunks)
        print(
            f"  {len(insights)} insights → {total} image(s) for {gnews_id}"
        )

        urls: list[str] = []
        for idx, chunk in enumerate(chunks):
            chunk_content = (
                f"KEY INSIGHTS:\n"
                + "\n".join(chunk)
                + "\n\n"
                + abbrev_block
            )
            # Naming: first image keeps gnews_id.png (backward compat)
            file_id = gnews_id if idx == 0 else f"{gnews_id}_{idx + 1}"
            url = self._generate_single_image(chunk_content, file_id)
            if url:
                urls.append(url)

        return urls

    def _generate_single_image(self, bullet_points: str, file_id: str) -> Optional[str]:
        """
        Core image generation call.
        `file_id` is used as the filename (file_id.png) — may differ from gnews_id
        when generating part 2, part 3 etc.
        """
        print(f"Generating image: {file_id}.png")
        prompt = f"""
        You will be given KEY INSIGHTS from an Indian stock market news article, and optionally
        a list of ABBREVIATIONS. These are your ONLY source of truth — do not use outside knowledge.

        Your task:

        - Read each KEY INSIGHT and decide the best VISUAL way to represent it
        - Identify the most important, factual, and data-backed elements per insight
        - Do NOT follow a fixed structure or predefined sections

        STRICT FACT ACCURACY RULE (CRITICAL)

        - Use ONLY numbers, percentages, dates, names, and data explicitly written in the input
        - Do NOT calculate derived percentages
        - Do NOT estimate ranges
        - Do NOT round numbers unless already rounded in the input
        - Do NOT add context from memory or prior knowledge
        - Do NOT infer causes unless directly mentioned
        - If a number is not clearly provided → do NOT display any number
        - If exact wording is unclear → omit it instead of guessing
        - Accuracy is more important than completeness

        TEXT CLARITY RULES (NON-NEGOTIABLE — prevents blur and incomplete text)

        - Every text label must be 100% COMPLETE — never cut off mid-word, mid-number, or mid-sentence
        - All text must be fully inside the image boundary — nothing touching or crossing any edge
        - Render all text at FULL OPACITY — no faded, semi-transparent, or ghost text
        - Every text element must sit on a solid or semi-transparent backing panel — never on a raw
          illustrated or gradient background
        - Minimum font sizes: key numbers 28px+, labels 18px+, supporting text 14px+
        - Always high contrast: white text on dark panel, dark text on light panel
        - Do NOT stylize, curve, rotate, or skew any text
        - Do NOT use outline-only (hollow) text — always solid fill
        - Never overlap two text elements — maintain clear separation between all labels

        NANO BANANA TEXT RULES

        - Do NOT write sentences or paragraphs inside the image
        - Use ONLY short text labels
        - Text must be bold, large, complete, and clearly readable
        - Prefer numbers, symbols, arrows, icons, and expressions over words
        - Do NOT place dense text anywhere in the image

        KEY RULES

        - Let the available data decide the layout
        - If numbers, percentages, or trends are present → represent them visually (charts, arrows, comparisons)
        - If explanations or reasons are present → show them using icons, symbols, or visual metaphors
        - If no clear data exists → use simple visual summaries (no invented charts)
        - Never assume, exaggerate, or fabricate missing information

        CONTENT HANDLING

        - Convert insights into visual-friendly cues — do NOT copy paragraphs
        - Preserve accuracy of all figures, names, and direction of movement
        - Avoid jargon wherever possible

        DESIGN GOAL

        - A highly engaging, scroll-stopping Instagram-style image
        - Viewer should understand the core message in 5–6 seconds
        - Mobile-first and Instagram-friendly
        - Each insight should be visually independent
        - Fill the entire canvas — large empty areas are not acceptable

        STYLE

        - Professional finance context with playful, engaging visuals
        - Light humor through visuals and emotions (not jokes or text)
        - Express market mood using characters, icons, or reactions
        - Avoid sensational, misleading, or clickbait visuals

        HUMOR & ENGAGEMENT GUIDELINES

        - Use expressive bull 🐂 / bear 🐻 characters where relevant
        - Use exaggerated but accurate emotions (excited, shocked, nervous, relaxed)
        - Humor should come from visual reactions, not from written jokes
        - Keep it addictive like an Instagram reel, but trustworthy

        ICON & VISUAL VARIABILITY RULE (VERY IMPORTANT)

        - Do NOT reuse the same icon style for every news article
        - For each new article, choose a different combination of:
            Minimalist flat icons | 3D emoji-style icons | Silhouette finance symbols
            Sticker-style illustrations | Line-art icons | Abstract geometric indicators
            Character-based expressions (only if mood-heavy news)
        - If one block uses arrows → next block should prefer icons or diagrams
        - Maintain stylistic consistency within ONE image, but vary across different articles
        - Avoid template-like repetition

        COLOR RULES

        - Randomly choose ONE primary color theme from:
            [dark green, royal blue, sunset orange, deep purple, charcoal black, crimson red, teal, mustard yellow]
        - Background and accent colors must align with the chosen theme
        - Do NOT reuse the same color theme intentionally

        OUTPUT

        - A single visual infographic-style image
        - Composed of multiple visual blocks or elements
        - Each element represents one KEY INSIGHT
        - Use charts, diagrams, icons, and minimal readable text only

        KEY TERMS GLOSSARY

        If the ABBREVIATIONS section below contains entries (not "(none)"):
        - Add a small "KEY TERMS" section at the very bottom of the image
        - COPY-PASTE RULE (ABSOLUTE): render each entry EXACTLY as written — do NOT add,
          remove, reword, or invent any abbreviation from your own knowledge
        - Format: compact pill badges — [BOLD TERM] = Full Form — two per row
        - Each badge must be wide enough to contain its full text — never clip or truncate
        - Minimum font: 14px TERM, 13px Full Form — fully opaque, high contrast
        - Keep it light and visually integrated — no heavy borders or thick boxes around it

        If ABBREVIATIONS says "(none)", skip the KEY TERMS section entirely.

        # ====================
        KEY NEWS INSIGHTS & ABBREVIATIONS
        {bullet_points}
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[prompt]
            )
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            img_dir = os.path.join(project_root, "news_images")
            os.makedirs(img_dir, exist_ok=True)
            filepath = os.path.join(img_dir, f"{file_id}.png")

            for part in response.parts:
                if part.text is not None:
                    print(part.text)
                elif part.inline_data is not None:
                    image = part.as_image()
                    image.save(filepath)
                    self.upload_blob(filepath, f"{file_id}.png")
                    break
        except Exception as e:
            print(f"Error generating image {file_id}: {e}")
            return None

        return f"https://storage.googleapis.com/{settings.GEMINI_BUCKET_NAME}/{file_id}.png"

    # Keep old name as a thin wrapper so nothing else breaks
    def generate_nano_banana_image(self, bullet_points: str, gnews_id: str) -> Optional[str]:
        return self._generate_single_image(bullet_points, gnews_id)


if __name__ == "__main__":
    gemini = GoogleGemini()
    sentiment = gemini.analyze_sentiment("The stock market is performing well today.", "123")
    print(f"Sentiment: {sentiment}")
    urls = gemini.generate_images_for_article("The stock market is performing well today.", "123")
    print(f"Images: {urls}")
