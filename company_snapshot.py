import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import asyncio
import httpx
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import time

# API Keys
SERPER_API_KEY = "768b1956ea4252916980afb7b0d7f31f8e5d2f37"
GEMINI_API_KEY = "AIzaSyAt_c0xgaXGg9H4oFX0YUqsQuhnV4gi7BY"

# AIonOS Capabilities
AIonOS_CAPABILITIES = (
    "AIonOS pioneers industry-specific Agentic AI solutions that autonomously solve "
    "complex business challenges while collaborating with human teams for optimal outcomes "
    "across travel, transport, hospitality, logistics, and telecom sectors."
)

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
    "Partnerships": "partners collaborations",
    "Company Challenges": "latest business challenges problems issues",
    "AIonOS Solutions": "AIonOS solutions"  # This will be handled separately
}

# Create a thread pool for CPU-bound tasks
thread_pool = ThreadPoolExecutor(max_workers=8)  # Increased workers

# Create a semaphore to limit concurrent API calls
API_SEMAPHORE = asyncio.Semaphore(5)  # Limit concurrent API calls

async def search_serper_async(client: httpx.AsyncClient, company_name: str, query: str, max_results: int = 1) -> List[str]:
    """Optimized search with reduced results and timeout."""
    try:
        async with API_SEMAPHORE:
            url = "https://google.serper.dev/search"
            headers = {"X-API-KEY": SERPER_API_KEY}
            payload = {
                "q": f"{company_name} {query}",
                "gl": "us",
                "hl": "en",
                "num": max_results
            }
            
            response = await client.post(url, json=payload, headers=headers, timeout=3.0)
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
    """Optimized content extraction with reduced processing."""
    try:
        async with API_SEMAPHORE:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = await client.get(url, headers=headers, timeout=3.0)
            response.raise_for_status()
            
            # Use BeautifulSoup in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            soup = await loop.run_in_executor(thread_pool, BeautifulSoup, response.text, "html.parser")
            
            # Remove unwanted elements more efficiently
            for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()
            
            # Extract text more efficiently
            text_elements = []
            for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']):
                text = tag.get_text(strip=True)
                if text and len(text) > 20:
                    text_elements.append(text)
                    if len(text_elements) >= 10:  # Limit number of elements
                        break
            
            text = "\n".join(text_elements)
            cleaned_text = clean_text(text)
            
            if len(cleaned_text) < 100:
                return None
                
            return cleaned_text[:5000]  # Reduced text length for faster processing
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

async def summarize_company_challenges(content: str, company_name: str) -> str:
    """Summarize company challenges using Gemini."""
    try:
        prompt = f"Summarize the main business challenges faced by {company_name} in 3-5 concise bullet points. Make sure points are relevant to the company challenges:\n\n{content[:3000]}"
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        return response.text.strip()
    except Exception:
        return "No specific information available"

async def generate_aionos_solutions(challenges_text: str) -> str:
    """Generate AIonOS solutions based on company challenges."""
    try:
        prompt = (
            f"Given the following company challenges in 3 to 4 consice bullet points:\n\n"
            f"{challenges_text}\n\n"
            f"How can AIonOS help solve these challenges based on its capabilities? Provide 3-4 concise bullet points:\n"
            f"{AIonOS_CAPABILITIES}\n\n"
            f"Respond in clear bullet points."
        )
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        return response.text.strip()
    except Exception:
        return "No specific information available"

async def process_section(client: httpx.AsyncClient, company_name: str, section: str, query: str) -> Tuple[str, Dict]:
    """Process a single section in parallel."""
    urls = await search_serper_async(client, company_name, query)
    tried_urls = []
    summary = ""
    content = ""
    
    for url in urls:
        content = await extract_content_async(client, url)
        if content:
            tried_urls.append(url)
            if section == "Company Challenges":
                summary = await summarize_company_challenges(content, company_name)
            else:
                summary = await summarize_section_content(content, section, company_name)
            if summary and "no specific information" not in summary.lower():
                return section, {"content": content, "urls": [url], "summary": summary}
    
    return section, {"content": "", "urls": tried_urls or urls, "summary": "No specific information available"}

async def generate_company_snapshot(company_name: str) -> dict:
    """Optimized main function with parallel processing."""
    if not company_name.strip():
        return {"error": "Please provide a valid company name."}
    
    start_time = time.time()
    section_content = {}
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        # Process all sections in parallel
        tasks = []
        for section, query in QUERIES.items():
            if section != "AIonOS Solutions":
                tasks.append(process_section(client, company_name, section, query))
        
        results = await asyncio.gather(*tasks)
        section_content = dict(results)
    
    if not any(v["content"] for v in section_content.values()):
        return {"error": "No content was collected for summarization. Please try a different company name."}
    
    snapshot = await summarize_snapshot_with_section_summaries(section_content, company_name)
    
    end_time = time.time()
    print(f"Total processing time: {end_time - start_time:.2f} seconds")
    
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
        "Partnerships",
        "Company Challenges",
        "AIonOS Solutions"
    ]
    
    # Process regular sections
    for section in company_sections:
        result["Company Snapshot"][section] = {
            "summary": section_content.get(section, {}).get("summary", "No specific information available"),
            "urls": section_content.get(section, {}).get("urls", [])
        }
    
    # Process initiative sections including challenges
    for section in initiative_sections[:-1]:  # Exclude AIonOS Solutions
        result["Initiatives"][section] = {
            "summary": section_content.get(section, {}).get("summary", "No specific information available"),
            "urls": section_content.get(section, {}).get("urls", [])
        }
    
    # Handle AIonOS Solutions separately
    challenges_text = section_content.get("Company Challenges", {}).get("summary", "")
    if challenges_text and "no specific information" not in challenges_text.lower():
        aionos_solutions = await generate_aionos_solutions(challenges_text)
        result["Initiatives"]["AIonOS Solutions"] = {
            "summary": aionos_solutions,
            "urls": []  # No URLs for AIonOS solutions as it's generated
        }
    else:
        result["Initiatives"]["AIonOS Solutions"] = {
            "summary": "No specific information available",
            "urls": []
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

        truncated_text = all_text[:20000]
        prompt = f"""Based on the following content about {company_name}, generate a detailed company snapshot in JSON format with these exact keys and their corresponding information:
        ensure the responses for each section are in 4 to 5 meaningful and authentic consice ponts and business-focused
        
{{
{{
    "Executive Summary": "What does the company do? and What is its mission, vision and value proposition? (Use bullet points)",
    "Key Facts": "When was it founded? Where is it headquartered(location/place)? How many employees? Is it public or private? What are its key geographies? (Use bullet points)",
    "Business Model & Revenue Streams": "How does the company generate revenue? Which products or services drive the business? (Use bullet points)",
    "Leadership": "Who are the key executives and leaders? (Use bullet points)",
}}
Initiatives:
{{    
    "Strategic Initiatives": "What are the company's strategic initiatives? (Use bullet points)",
    "Data Maturity & Initiatives": "How mature are the company's data stack and tech capabilites?What tools, dashboards and AI/ML use-cases power decision-making?(Use bullet points)",
    "Partnerships": "What are the company's partnerships? (Use bullet points)",
    
}}
}}
Content to analyze:
{truncated_text}

Instructions:
1. Generate a JSON object with the exact keys shown above
2. For each key, provide summary based on the content make sure the information is related to the company.
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
                    "Partnerships",
                    
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