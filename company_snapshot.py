import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import asyncio
import httpx
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

# API Keys
SERPER_API_KEY = "768b1956ea4252916980afb7b0d7f31f8e5d2f37"
GEMINI_API_KEY = "AIzaSyAgKdmYgZg-_jVt9wDqDgKPd2ow_OKGrgU"

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-lite")

# Define information queries with optimized search terms
QUERIES = {
    "Key Facts": "company overview headquarters employees",
    "Leadership": "executives management team",
    "Strategic Initiatives": "strategy initiatives",
    "Partnerships": "partners collaborations"
}

# Create a thread pool for CPU-bound tasks
thread_pool = ThreadPoolExecutor(max_workers=4)

async def search_serper_async(client: httpx.AsyncClient, company_name: str, query: str, max_results: int = 2) -> List[str]:
    try:
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": SERPER_API_KEY}
        payload = {
            "q": f"{company_name} {query}",
            "gl": "us",
            "hl": "en",
            "num": max_results
        }
        
        response = await client.post(url, json=payload, headers=headers, timeout=5.0)
        response.raise_for_status()
        results = response.json()
        
        if not results.get("organic"):
            return []
            
        valid_urls = []
        for result in results["organic"]:
            if result.get("link") and not any(x in result["link"].lower() for x in ["youtube.com", "facebook.com", "twitter.com", "linkedin.com"]):
                valid_urls.append(result["link"])
                if len(valid_urls) >= max_results:
                    break
                    
        return valid_urls
    except Exception:
        return []

async def extract_content_async(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = await client.get(url, headers=headers, timeout=5.0)
        response.raise_for_status()
        
        # Use BeautifulSoup in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        soup = await loop.run_in_executor(thread_pool, BeautifulSoup, response.text, "html.parser")
        
        # Remove unwanted elements
        for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
            
        # Extract text from paragraphs and other relevant elements
        text_elements = []
        for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']):
            text = tag.get_text(strip=True)
            if text and len(text) > 20:
                text_elements.append(text)
                
        text = "\n".join(text_elements)
        cleaned_text = clean_text(text)
        
        if len(cleaned_text) < 100:
            return None
            
        return cleaned_text[:10000]  # Limit text length for faster processing
    except Exception:
        return None

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    text = ''.join(char for char in text if char.isprintable())
    return text.strip()

async def summarize_snapshot(all_text: str, company_name: str) -> str:
    try:
        # Limit text length for faster processing
        truncated_text = all_text[:15000]
        
        prompt = f"""Based on the following content about {company_name}, generate a detailed company snapshot in JSON format with these exact keys and their corresponding information:

{{
    "Executive Summary": "What does the company do? What is its mission, vision and value proposition?",
    "Key Facts": "When was it founded? Where is it headquartered? How many employees? Is it public or private? What are its key geographies?",
    "Business Model & Revenue Streams": "How does the company generate revenue? Which products or services drive the business?",
    "Leadership": "Who are the key executives and leaders?",
    "Strategic Initiatives": "What are the company's strategic initiatives?",
    "Data Maturity & Initiatives": "What are the company's data maturity initiatives?",
    "Partnerships": "What are the company's partnerships?"
}}

Content to analyze:
{truncated_text}

Instructions:
1. Generate a JSON object with the exact keys shown above
2. For each key, provide a concise summary based on the content
3. If information for a section is not found, use "No specific information available"
4. Use bullet points where appropriate
5. Keep responses concise and business-focused
6. Return ONLY the JSON object, no additional text"""

        # Run Gemini in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        response_text = response.text.strip()
        
        # Clean up the response text
        response_text = response_text.replace('```json', '').replace('```', '')
        
        # Find and parse JSON
        import re
        import json
        
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return create_error_response()
        return create_error_response()
    except Exception:
        return create_error_response()

def create_error_response() -> Dict[str, str]:
    return {
        "Executive Summary": "Error processing company information",
        "Key Facts": "Error processing company information",
        "Business Model & Revenue Streams": "Error processing company information",
        "Leadership": "Error processing company information",
        "Strategic Initiatives": "Error processing company information",
        "Data Maturity & Initiatives": "Error processing company information",
        "Partnerships": "Error processing company information"
    }

async def generate_company_snapshot(company_name: str) -> Dict[str, str]:
    if not company_name.strip():
        return {"error": "Please provide a valid company name."}
        
    collected_text = ""
    successful_sections = 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Create tasks for all queries
        tasks = []
        for section, query in QUERIES.items():
            tasks.append(search_serper_async(client, company_name, query))
        
        # Wait for all searches to complete
        search_results = await asyncio.gather(*tasks)
        
        # Process results and extract content
        for urls in search_results:
            if not urls:
                continue
                
            # Try to get content from the first valid URL
            for url in urls:
                content = await extract_content_async(client, url)
                if content:
                    collected_text += f"\n\n{content}"
                    successful_sections += 1
                    break

    if successful_sections == 0:
        return {"error": "No content was collected for summarization. Please try a different company name."}

    snapshot = await summarize_snapshot(collected_text, company_name)
    return {"snapshot": snapshot} 