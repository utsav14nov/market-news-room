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
        You will be given two sections extracted from an Indian stock market news article:
          KEY INSIGHTS   — rich, fact-based bullet points with numbers and context
          ABBREVIATIONS  — professional financial terms and their full forms (may be "(none)")

        These are your ONLY source of truth. Do not use outside knowledge.

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        STRICT FACT ACCURACY (CRITICAL)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        - Use ONLY numbers, names, and data that appear verbatim in the input below
        - Do NOT round, estimate, or derive any values not explicitly given
        - Do NOT add context from your own knowledge
        - If a value is unclear → omit it, never guess

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        IMAGE LAYOUT — FREE-FLOWING, EDITORIAL
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        MAIN CONTENT — one visual card per KEY INSIGHT
        - Each card is a self-contained visual story
        - Each card has THREE lines of text — ALL THREE must appear, never skip any:
            Line 1 (HEADLINE): bold, largest font — key number, entity, or action
            Line 2 (CONTEXT):  medium font — cause, source, or supporting fact
            Line 3 (IMPACT):   smaller font — consequence or additional data point
          Reduce card height rather than dropping any line. All 3 must be visible.
        - One supporting visual per card: icon, arrow, bar chart, or diagram
        - Cards flow naturally down the image — organic arrangement, varying sizes,
          asymmetric columns, cards offset or overlapping slightly — make it feel alive
        - Separate cards ONLY with whitespace and subtle color shifts
        - ABSOLUTELY NO thick horizontal bars, heavy ruled lines, or rigid grid dividers
          between cards. Use ≤1px lines or soft shadows at most.

        KEY TERMS GLOSSARY (skip entirely if ABBREVIATIONS says "(none)")
        ── COPY-PASTE RULE (ABSOLUTE) ────────────────────────────────────
        - Read the ABBREVIATIONS section from the input below
        - Render EACH entry EXACTLY as written — do NOT add, remove, or reword
        - Do NOT invent abbreviations from your own knowledge
        ──────────────────────────────────────────────────────────────────
        - Float naturally at the bottom of the image, seamlessly integrated with design
        - DO NOT surround with a heavy bordered box or thick strip — keep it light
        - Small compact badges: [BOLD TERM] = [Full Form], two badges per row
        - Each badge auto-sizes to fit its full text — never clip or truncate
        - Minimum font: 14px TERM, 13px Full Form

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        TEXT CLARITY RULES (NON-NEGOTIABLE)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        - Every text element MUST sit inside a solid or semi-transparent filled panel
        - Never place text directly on a complex/gradient/illustrated background
        - Minimum internal padding of every text container: 10px all sides
        - Minimum gap between any two text containers: 14px
        - Text MUST NEVER overflow, clip, or run off its container
          → shorten a label rather than letting it overflow
        - Never place two labels so close they visually merge
        - High contrast between text colour and its background panel (pass WCAG AA)
        - Minimum font sizes: key numbers 30px+, headlines 20px+, detail lines 15px+
        - NO curved, rotated, skewed, or outlined (hollow) text — always solid filled

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        VISUAL STYLE
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        - Professional finance context with engaging, playful visuals
        - Express market mood with bull 🐂 / bear 🐻 characters or expressive icons
        - Humor comes from visual reactions, not written text
        - Avoid sensational, misleading, or clickbait imagery

        ICON VARIETY: pick a DIFFERENT style per article
        - Mix from: minimalist flat, 3D emoji-style, silhouette symbols, sticker, line-art, geometric
        - Alternate visual treatment across insight blocks within the same image

        COLOR: ONE randomly chosen theme from
          [dark green · royal blue · sunset orange · deep purple · charcoal black · crimson red · teal · mustard yellow]
        - Background and accents align with the theme
        - KEY TERMS strip uses a darker/muted variant of the same theme

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        CANVAS USAGE — CRITICAL
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        - Fill the ENTIRE canvas — large empty areas are forbidden
        - Cards must be compact and information-dense; shrink card size and reduce padding
          until all insight cards together cover at least 90% of the canvas
        - If you have fewer insights, make each card taller / richer to fill the space
        - Viewers expect a packed, rich infographic — not a sparse poster with lots of air
        - Tight but readable: minimum breathing room between cards, no wasted whitespace

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        DESIGN GOAL
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        - Instagram-style portrait infographic, mobile-first
        - Viewer understands the full story in 5–8 seconds
        - Each insight block tells a complete mini-story (headline + context + impact)
        - KEY TERMS badges help any reader decode jargon instantly

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
