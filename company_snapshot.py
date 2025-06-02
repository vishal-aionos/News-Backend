import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import asyncio
import httpx
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

# API Keys
SERPER_API_KEY = "768b1956ea4252916980afb7b0d7f31f8e5d2f37"
GEMINI_API_KEY = "AIzaSyAt_c0xgaXGg9H4oFX0YUqsQuhnV4gi7BY"

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-lite")

# Define information queries with optimized search terms
QUERIES = {
    "Executive Summary": "company overview mission vision value proposition",
    "Key Facts": "company overview headquarters employees",
    "Business Model & Revenue Streams": "revenue products services",
    "Leadership": "executives management team",
    "Strategic Initiatives": "strategy initiatives",
    "Data Maturity & Initiatives": "data initiatives",
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

async def summarize_section_content(content: str, section: str, company_name: str) -> str:
    """Summarize a single section's content using Gemini."""
    try:
        prompt = f"Summarize the following content for the section '{section}' of {company_name} in 5-7 business-focused bullet points. If no relevant information, say 'No specific information available'.\nContent:\n{content[:3000]}"
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        summary = response.text.strip()
        return summary
    except Exception:
        return "No specific information available"

async def generate_company_snapshot(company_name: str) -> dict:
    if not company_name.strip():
        return {"error": "Please provide a valid company name."}
    section_content = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = []
        for section, query in QUERIES.items():
            tasks.append(search_serper_async(client, company_name, query))
        search_results = await asyncio.gather(*tasks)
        for (section, _), urls in zip(QUERIES.items(), search_results):
            tried_urls = []
            summary = ""
            for url in urls:
                content = await extract_content_async(client, url)
                if content:
                    tried_urls.append(url)
                    summary = await summarize_section_content(content, section, company_name)
                    if summary and "no specific information" not in summary.lower():
                        section_content[section] = {"content": content, "urls": [url], "summary": summary}
                        break
            else:
                # If no valid summary found, fallback
                section_content[section] = {"content": "", "urls": tried_urls or urls, "summary": "No specific information available"}
    if not any(v["content"] for v in section_content.values()):
        return {"error": "No content was collected for summarization. Please try a different company name."}
    snapshot = await summarize_snapshot_with_section_summaries(section_content, company_name)
    return {"snapshot": snapshot}

async def summarize_snapshot_with_section_summaries(section_content: dict, company_name: str) -> dict:
    # This function will use the already summarized content for each section
    # and build the final JSON structure as before
    result = {"Company Snapshot": {}, "Initiatives": {}}
    company_sections = [
        "Executive Summary",
        "Key Facts",
        "Business Model & Revenue Streams",
        "Leadership"
    ]
    initiative_sections = [
        "Strategic Initiatives",
        "Data Maturity & Initiatives",
        "Partnerships"
    ]
    for section in company_sections:
        result["Company Snapshot"][section] = {
            "summary": section_content.get(section, {}).get("summary", "No specific information available"),
            "urls": section_content.get(section, {}).get("urls", [])
        }
    for section in initiative_sections:
        result["Initiatives"][section] = {
            "summary": section_content.get(section, {}).get("summary", "No specific information available"),
            "urls": section_content.get(section, {}).get("urls", [])
        }
    return result

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

async def summarize_snapshot(section_content: dict, company_name: str) -> dict:
    try:
        # Concatenate all content for the prompt, but keep section mapping
        all_text = ""
        for section, data in section_content.items():
            if data["content"]:
                all_text += f"\n\n--- {section} ---\n{data['content']}"

        truncated_text = all_text[:15000]
        prompt = f"""Based on the following content about {company_name}, generate a detailed company snapshot in JSON format with these exact keys and their corresponding information:
        Keep responses 5 to 7 sentences and business-focused
{{
Company Snapshot:
{{
    "Executive Summary": "What does the company do? What is its mission, vision and value proposition? (Use bullet points)",
    "Key Facts": "When was it founded? Where is it headquartered? How many employees? Is it public or private? What are its key geographies? (Use bullet points)",
    "Business Model & Revenue Streams": "How does the company generate revenue? Which products or services drive the business? (Use bullet points)",
    "Leadership": "Who are the key executives and leaders? (Use bullet points)",
}}
Initiatives:
{{    
    "Strategic Initiatives": "What are the company's strategic initiatives? (Use bullet points)",
    "Data Maturity & Initiatives": "How mature are the company's data stack and tech capabilites?What tools, dashboards and AI/ML use-cases power decision-making?(Use bullet points)",
    "Partnerships": "What are the company's partnerships? (Use bullet points)"
}}
}}
Content to analyze:
{truncated_text}

Instructions:
1. Generate a JSON object with the exact keys shown above
2. For each key, provide a detailedsummary based on the content make sure the information is related to the company.
3. If information for a section is not found, use "No specific information available"
4. Use bullet points for every section (start each point with '•')
5. Return ONLY the JSON object, no additional text"""
        import re
        import json
        # Run Gemini in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        response_text = response.text.strip()
        response_text = response_text.replace('```json', '').replace('```', '')
        
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                summary = json.loads(json_str)
                # Build the result with top-level keys 'Company Snapshot' and 'Initiatives'
                result = {"Company Snapshot": {}, "Initiatives": {}}
                company_sections = [
                    "Executive Summary",
                    "Key Facts",
                    "Business Model & Revenue Streams",
                    "Leadership"
                ]
                initiative_sections = [
                    "Strategic Initiatives",
                    "Data Maturity & Initiatives",
                    "Partnerships"
                ]
                # Fill Company Snapshot
                for section in company_sections:
                    result["Company Snapshot"][section] = {
                        "summary": summary.get("Company Snapshot", {}).get(section, ""),
                        "urls": section_content.get(section, {}).get("urls", [])
                    }
                # Fill Initiatives
                for section in initiative_sections:
                    result["Initiatives"][section] = {
                        "summary": summary.get("Initiatives", {}).get(section, ""),
                        "urls": section_content.get(section, {}).get("urls", [])
                    }
                return result
            except json.JSONDecodeError:
                return create_error_response()
        return create_error_response()
    except Exception:
        return create_error_response() 