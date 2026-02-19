from .config import settings
from google import genai
import json
import os
from PIL import Image
from google.cloud import storage

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

        # Optional: set a generation-match precondition to avoid potential race conditions
        # and data corruptions. The request to upload is aborted if the object's
        # generation number does not match your precondition. For a destination
        # object that does not yet exist, set the if_generation_match precondition to 0.
        # If the destination object already exists in your bucket, set instead a
        # generation-match precondition using its generation number.
        generation_match_precondition = 0

        blob.upload_from_filename(source_file_name, if_generation_match=generation_match_precondition)

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
    
    def generate_nano_banana_image(self, news_text: str, gnews_id: str):
        print(f"Generating image for {gnews_id}")
        prompt = f"""
        You will be given a FULL news article related to the Indian stock market.

        Your task:

        - Read and understand the entire content internally
        - Identify the most important, factual, and data-backed insights
        - Decide the best VISUAL way to explain each insight
        - Do NOT follow a fixed structure or predefined sections

        STRICT FACT ACCURACY RULE (CRITICAL)

        - Use ONLY numbers, percentages, dates, names, and data that are explicitly written in the provided news content
        - Do NOT calculate derived percentages
        - Do NOT estimate ranges
        - Do NOT round numbers unless already rounded in the article
        - Do NOT add context from memory or prior knowledge
        - Do NOT infer causes unless directly mentioned
        - If a number is not clearly provided → do NOT display any number
        - If exact wording is unclear → omit it instead of guessing
        - If information is missing, leave it out.
        - Accuracy is more important than completeness.
        
        VERY IMPORTANT (NANO BANANA TEXT RULES):

        - Do NOT write sentences or paragraphs inside the image
        - Use ONLY short text labels
        - Text must be bold, large, complete, and clearly readable
        - Prefer numbers, symbols, arrows, icons, and expressions over words
        - Do NOT stylize or curve text
        - Do NOT place dense text anywhere in the image

        KEY RULES:

        - Let the available data decide the layout
        - If numbers, percentages, or trends are present → represent them visually (charts, arrows, comparisons)
        - If explanations or reasons are present → show them using icons, symbols, or visual metaphors
        - If no clear data exists → use simple visual summaries (no invented charts)
        - Never assume, exaggerate, or fabricate missing information

        CONTENT HANDLING:

        - Extract insights internally; do NOT copy paragraphs or headlines
        - Convert long explanations into visual-friendly cues
        - Preserve accuracy of all figures, names, and direction of movement
        - Avoid jargon wherever possible

        DESIGN GOAL:

        - A highly engaging, scroll-stopping Instagram-style image
        - Viewer should understand the core message in 5–6 seconds
        - Mobile-first and Instagram-friendly
        - Each insight should be visually independent

        STYLE:

        - Professional finance context with playful, engaging visuals
        - Light humor through visuals and emotions (not jokes or text)
        - Express market mood using characters, icons, or reactions
        - Avoid sensational, misleading, or clickbait visuals

        HUMOR & ENGAGEMENT GUIDELINES:

        - Use expressive bull 🐂 / bear 🐻 characters where relevant
        - Use exaggerated but accurate emotions (excited, shocked, nervous, relaxed)
        - Humor should come from visual reactions, not from written jokes
        - Keep it addictive like an Instagram reel, but trustworthy

        ICON & VISUAL VARIABILITY RULE (VERY IMPORTANT)

        - To avoid repetitive visuals:

        - Do NOT reuse the same icon style for every news article
        - For each new article:
            - Choose a different combination of:
            - Minimalist flat icons
            - 3D emoji-style icons
            - Silhouette finance symbols
            - Sticker-style illustrations
            - Line-art icons
            - Abstract geometric indicators
            - Character-based expressions (only if mood-heavy news)
        - If previous block uses arrows → next block should prefer icons or diagrams
        - If previous insight uses character emotion → next one should use clean data visuals
        - Maintain stylistic consistency within ONE image, but vary approach across different news articles
        - Avoid template-like repetition.

        ### Color rules:

        - Randomly choose ONE primary color theme from this list for every generation:
            
            [dark green, royal blue, sunset orange, deep purple, charcoal black, crimson red, teal, mustard yellow]
            
        - Background and accent colors must align with the chosen theme.
        - Do NOT reuse the same color theme intentionally.

        OUTPUT:

        - A single visual infographic-style image
        - Composed of multiple visual blocks or elements
        - Each element represents one important insight from the article
        - Use charts, diagrams, icons, and minimal readable text only

        # ====================
        FULL NEWS CONTENT
        {news_text}
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[prompt]
            )
            # Save to project_root/news_images/ so it works regardless of cwd
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            img_dir = os.path.join(project_root, "news_images")
            os.makedirs(img_dir, exist_ok=True)
            filepath = os.path.join(img_dir, f"{gnews_id}.png")

            for part in response.parts:
                if part.text is not None:
                    print(part.text)
                elif part.inline_data is not None:
                    image = part.as_image()
                    image.save(filepath)
                    self.upload_blob(filepath, f"{gnews_id}.png")
                    break
        except Exception as e:
            print(f"Error from Gemini for {gnews_id}: {e}")
            return None

        return f"https://storage.googleapis.com/{settings.GEMINI_BUCKET_NAME}/{gnews_id}.png"

if __name__ == "__main__":
    gemini = GoogleGemini()
    sentiment = gemini.analyze_sentiment("The stock market is performing well today.", "123")
    print(f"Sentiment: {sentiment}")
    image = gemini.generate_nano_banana_image("The stock market is performing well today.", "123")
    print(f"Image: {image}")