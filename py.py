import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import asyncio
import httpx
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import time
import json
import fitz  # PyMuPDF
import io
import aiohttp

# API Keys
SERPER_API_KEY = "d38fff68cf3c2e994f15273fb1f8dc5743535d2b"
GEMINI_API_KEY = "AIzaSyAt_c0xgaXGg9H4oFX0YUqsQuhnV4gi7BY"

# AIonOS Capabilities
AIonOS_CAPABILITIES = (
     """Agentic Assistants & Customer Experience
ConciergeAgent/Mate – Real-time voice/text assistant for end-to-end journey support and disruption management.

IntelliConverse – Multilingual AI interface for seamless support across voice, chat, and messaging channels.

IntelliEmail – Automated email engine for confirmations, updates, and customer notifications.

IntelliVoice – Natural language assistant for bookings, changes, and cancellations.

IntelliSurvey – Conversational feedback tool to capture post-service insights.

IntelliSocial – Real-time social engagement tool for responding to customer signals and brand mentions.

AI & Analytics Engines
IntelliPulse – Dashboard monitoring sentiment, compliance, and agent-customer interactions.

IntelliRAG – Retrieval-Augmented Generation system delivering accurate, policy-compliant agent responses.

IntelliReach – Personalization engine for contextual journey recommendations and banking offers.

IntelliMarketing – AI-driven campaign engine optimizing personalization and targeting.

IntelliFinCrime – Financial crime detection tool for monitoring fraud, AML, and anomalies.

IntelliRegTech – Compliance assistant automating regulatory tracking and audit documentation.

IntelliResilience – AI-powered system for predictive recovery, failover, and SLA assurance.

IntelliSustain – ESG monitoring platform tracking emissions, waste, and regulatory compliance.

Operations & Workflow Automation
IntelliWorkflow – AI-driven orchestration of complex cross-functional business processes.

Smart Exchange – Platform for reconciling and exchanging logistics and trade financial data.

Smart Verify – Identity verification engine combining authentication, fraud detection, and user context.

Industry Platforms & Infrastructure
Freight Forwarding System (FFS) – End-to-end logistics platform managing multimodal shipments, CRM, billing, and documentation.

Warehouse Management System – Streamlines inbound/outbound processes, inventory, and reporting.

Dynamic Workforce Tracking – Real-time tracking of vehicles and workforce across the supply chain.

Smart Building Management – Centralized control and optimization of building systems and assets.

Data & Collaboration
Data Collaboration Platform – Consent-based data mesh enabling secure internal and external data sharing.

AionOS delivers industry-specific Agentic AI solutions that autonomously address complex business challenges while enhancing human collaboration—driving innovation across travel, logistics, hospitality, telecom, and transport."""
)

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# Create thread pool and semaphore
thread_pool = ThreadPoolExecutor(max_workers=8)
API_SEMAPHORE = asyncio.Semaphore(5)

async def search_serper_async(client: httpx.AsyncClient, company_name: str, query: str, max_results: int = 3) -> List[str]:
    """Search using Serper API with a single optimized query."""
    try:
        async with API_SEMAPHORE:
            # Single comprehensive query that includes the year to get recent results
            search_query = f"{company_name} recent {query}"
            
            url = "https://google.serper.dev/search"
            headers = {"X-API-KEY": SERPER_API_KEY}
            payload = {
                "q": search_query,
                "gl": "us",
                "hl": "en",
                "num": max_results
            }
            
            response = await client.post(url, json=payload, headers=headers, timeout=3.0)
            response.raise_for_status()
            results = response.json()
            
            all_urls = []
            if results.get("organic"):
                for result in results["organic"]:
                    if result.get("link") and not any(x in result["link"].lower() for x in ["youtube.com", "facebook.com", "twitter.com", "linkedin.com"]):
                        if result["link"] not in all_urls:
                            all_urls.append(result["link"])
                            if len(all_urls) >= max_results:
                                break
            
            return all_urls
    except Exception:
        return []

async def extract_content_async(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Extract and clean content from a URL."""
    try:
        async with API_SEMAPHORE:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = await client.get(url, headers=headers, timeout=3.0)
            response.raise_for_status()
            
            loop = asyncio.get_event_loop()
            soup = await loop.run_in_executor(thread_pool, BeautifulSoup, response.text, "html.parser")
            
            for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'iframe', 'form', 'button']):
                element.decompose()
            
            text_elements = []
            main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=['content', 'main', 'article'])
            if main_content:
                soup = main_content
            
            for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'div']):
                text = tag.get_text(strip=True)
                if text and len(text) > 20 and not any(x in text.lower() for x in ['cookie', 'privacy policy', 'terms of service']):
                    text_elements.append(text)
                    if len(text_elements) >= 15:
                        break
            
            text = "\n".join(text_elements)
            cleaned_text = clean_text(text)
            
            if len(cleaned_text) < 100:
                return None
                
            return cleaned_text[:5000]
    except Exception:
        return None

def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text:
        return ""
    text = " ".join(text.split())
    text = ''.join(char for char in text if char.isprintable())
    return text.strip()

async def extract_pdf_content(url: str) -> Optional[str]:
    """Extract text content from a PDF URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    pdf_data = await response.read()
                    pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
                    text = ""
                    for page in pdf_document:
                        text += page.get_text()
                    pdf_document.close()
                    return text[:10000]  # Limit text length
    except Exception as e:
        print(f"Error extracting PDF content: {str(e)}")
    return None

async def get_executive_summary(client: httpx.AsyncClient, company_name: str) -> Dict:
    """Get executive summary section."""
    urls = await search_serper_async(client, company_name, "company overview ")
    content = ""
    tried_urls = []
    
    for url in urls:
        content = await extract_content_async(client, url)
        if content:
            tried_urls.append(url)
            # Summarize the found content
            prompt = f"""Analyze the following content about {company_name} and create a concise five-point summary . Each point should be one short sentence covering what the company does, its mission and vision, value proposition, core business focus, and market position. If any information is unavailable or missing then provide details based on your latest knowledge."

Content to summarize:
{content[:5000]}

Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]"""
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
            content = response.text.strip()
            break
    
    if not content:
        prompt = f"""Based on the following information about {company_name}, write a concise five-point summary. Each point should be a single short sentence covering what the company does, its mission and vision, value proposition, core business focus, and market position. Do not include any side headings, subheadings, introductions, or conclusions.

Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        content = response.text.strip()
    
    return {
        "summary": content,
        "urls": tried_urls
    }

async def get_key_facts(client: httpx.AsyncClient, company_name: str) -> Dict:
    """Get key facts section."""
    urls = await search_serper_async(client, company_name, "company overview")
    content = ""
    tried_urls = []
    
    for url in urls:
        content = await extract_content_async(client, url)
        if content:
            tried_urls.append(url)
            # Summarize the found content
            prompt = f"""Based on this content about {company_name}, extract key facts in this exact format:
If any information is unavailable or missing from the content, fill it in using your latest knowledge without stating that the information was missing or inferred — just give the final answer.
• Established: [year]
• Headquarters: [location]
• Number of employees: [number]
• Public/Private: [status]
• Key geographies: [locations]

Content to analyze:
{content[:5000]}
 """
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
            content = response.text.strip()
            break
    
    if not content:
        prompt = f"""Provide key facts about {company_name} in this exact format:
• Established: [year]
• Headquarters: [location]
• Number of employees: [number]
• Public/Private: [status]
• Key geographies: [locations]"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        content = response.text.strip()
    
    return {
        "summary": content,
        "urls": tried_urls
    }

async def get_business_model(client: httpx.AsyncClient, company_name: str) -> Dict:
    """Get business model section."""
    urls = await search_serper_async(client, company_name, "products services revenue model")
    content = ""
    tried_urls = []
    
    for url in urls:
        content = await extract_content_async(client, url)
        if content:
            tried_urls.append(url)
            # Summarize the found content
            prompt = f"""Analyze the following content about {company_name} and provide a concise five-point summary. Each point should be one short sentence that addresses revenue streams, main products or services, business model type, target markets, and competitive advantages. Do not include any side headings, subheadings, introductions, or conclusions.
If any information is unavailable or missing from the content, fill it in using your latest knowledge without stating that the information was missing or inferred — just give the final answer.
Content to analyze:
{content}

Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]"""
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
            content = response.text.strip()
            break
    
    if not content:
        prompt = f"""Based on the following information about {company_name}, provide a five-point summary. Each point should be one short sentence covering revenue streams, main products or services, business model type, target markets, and competitive advantages. Do not include any side headings, subheadings, introductions, or conclusions in the output.

Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        content = response.text.strip()
    
    return {
        "summary": content,
        "urls": tried_urls
    }

async def get_leadership(client: httpx.AsyncClient, company_name: str) -> Dict:
    """Get leadership section."""
    urls = await search_serper_async(client, company_name, "executives management team")
    content = ""
    tried_urls = []
    
    for url in urls:
        content = await extract_content_async(client, url)
        if content:
            tried_urls.append(url)
            # Summarize the found content
            prompt = f"""Review the following content about {company_name} and extract key facts in the below format. Begin each point with a bullet (•) and do not include any headings, introductions, or additional commentary.
If any information is unavailable or missing from the content, fill it in using your latest knowledge without stating that the information was missing or inferred — just give the final answer.

Format:
• CEO / Managing Director: [Full Name]
• Founder(s): [Full Name(s)]
• Chairperson: [Full Name]
• Board of Directors:[Name  & Role/Title]
• Recent Changes: [short sentence] 

Content to analyze:
{content[:10000]}"""
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
            content = response.text.strip()
            break
    
    if not content:
        prompt = f"""Using the following information about {company_name}, create a five-point summary. Each point should be one short sentence that covers key executives, leadership structure, notable positions, recent changes, and leadership style or approach. Do not include any side headings, subheadings, introductions, or conclusions in the output.

Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        content = response.text.strip()
    
    return {
        "summary": content,
        "urls": tried_urls
    }

async def get_strategic_initiatives(client: httpx.AsyncClient, company_name: str) -> Dict:
    """Get strategic initiatives section."""
    urls = await search_serper_async(client, company_name, "strategy initiatives")
    content = ""
    tried_urls = []
    
    for url in urls:
        content = await extract_content_async(client, url)
        if content:
            tried_urls.append(url)
            # Summarize the found content
            prompt = f"""Analyze the following content about {company_name} and summarize its strategic initiatives in exactly five bullet points. Each point should be one concise sentence, and the output must not include any side headings, subheadings, introductions, or conclusions. The summary should reflect current initiatives, future plans, strategic focus areas, transformation efforts, and growth strategies.
If any information is unavailable or missing from the content, fill it in using your latest knowledge without stating that the information was missing or inferred — just give the final answer.
Content to analyze:
{content}

Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]"""
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
            content = response.text.strip()
            break
    
    if not content:
        prompt = f"""Using the following information about {company_name}, create a five-point summary in bullet format. Each point should be one short sentence that covers current initiatives, future plans, strategic focus areas, transformation efforts, and growth strategies. Do not include any side headings, subheadings, introductions, or conclusions in the output.

Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        content = response.text.strip()
    
    return {
        "summary": content,
        "urls": tried_urls
    }

async def get_data_maturity(client: httpx.AsyncClient, company_name: str) -> Dict:
    """Get data maturity section."""
    urls = await search_serper_async(client, company_name, "data initiatives tech stack")
    content = ""
    tried_urls = []
    
    for url in urls:
        content = await extract_content_async(client, url)
        if content:
            tried_urls.append(url)
            # Summarize the found content
            prompt = f"""Analyze the following content about {company_name} and provide a five-point summary. Each point should be one short sentence covering data capabilities, tech stack, AI/ML initiatives, digital transformation, and data-driven decision making. Do not include any side headings, subheadings, introductions, or conclusions.
If any information is unavailable or missing from the content, fill it in using your latest knowledge without stating that the information was missing or inferred — just give the final answer.
Content to analyze:
{content[:5000]}

Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]
"""
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
            content = response.text.strip()
            break
    
    if not content:
        prompt = f"""Using the following information about {company_name}, create a five-point summary. Each point should be one short sentence covering data capabilities, tech stack, AI/ML initiatives, digital transformation, and data-driven decision making. Do not include any side headings, subheadings, introductions, or conclusions in the output.

Format:
• [point 1]
• [point 2]
• [point 3]
• [point 4]
• [point 5]"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        content = response.text.strip()
    
    return {
        "summary": content,
        "urls": tried_urls
    }

async def get_partnerships(client: httpx.AsyncClient, company_name: str) -> Dict:
    """Get partnerships section."""
    urls = await search_serper_async(client, company_name, "partnerships collaborations")
    content = ""
    tried_urls = []
    
    for url in urls:
        content = await extract_content_async(client, url)
        if content:
            tried_urls.append(url)
            # Summarize the found content
            prompt = f"""Analyze the following content about {company_name} and provide a five-point summary in bullet format. Each point should be one short sentence covering key partnerships, strategic alliances, joint ventures, industry collaborations, and overall partnership strategy. Do not include any side headings, subheadings, introductions, or conclusions.
If any information is unavailable or missing from the content, fill it in using your latest knowledge without stating that the information was missing or inferred — just give the final answer.
Content to analyze:
{content[:5000]}

Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]"""
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
            content = response.text.strip()
            break
    
    if not content:
        prompt = f"""Using the following information about {company_name}, create a five-point summary. Each point should be one short sentence covering key partnerships, strategic alliances, joint ventures, industry collaborations, and partnership strategy. Do not include any side headings, subheadings, introductions, or conclusions in the output.
If any information is unavailable or missing from the content, fill it in using your latest knowledge without stating that the information was missing or inferred — just give the final answer.
Format:
[point 1]
[point 2]
[point 3]
[point 4]
[point 5]"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        content = response.text.strip()
    
    return {
        "summary": content,
        "urls": tried_urls
    }

async def get_challenges_and_solutions(client: httpx.AsyncClient, company_name: str) -> Dict:
    """Get challenges and AIonOS solutions section."""
    final_output = []
    tried_urls = []
    
    # Search for challenges from web
    web_urls = await search_serper_async(client, company_name, "challenges", max_results=3)
    
    # Process web content
    for url in web_urls:
        content = await extract_content_async(client, url)
        if content:
            tried_urls.append(url)
            prompt = f"""Based on this content about {company_name}'s challenges:
{content}

And considering AIonOS's capabilities:
{AIonOS_CAPABILITIES}

Extract up to two distinct challenges and provide corresponding AIonOS solutions. For each:
Clearly state a specific Challenge the company is facing in one short sentence.
Immediately follow it with a corresponding AIonOS Solution be more creative to solve the challenge for specific in one short sentence.

Format each entry exactly as:
Challenge: [One short sentence]
AIonOS Solution: [One short sentence]
URL: {url}

Challenge: [One short sentence]
AIonOS Solution: [One short sentence]
URL: {url}"""

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
            challenges = response.text.strip()
            if challenges:
                final_output.append(challenges)
    
    # Search for annual report PDFs
    pdf_urls = await search_serper_async(client, company_name, "latest annual report filetype:pdf", max_results=1)
    
    # Process PDF content
    for url in pdf_urls:
        content = await extract_pdf_content(url)
        if content:
            tried_urls.append(url)
            prompt = f"""Based on this annual report content about {company_name}'s challenges:
{content}

And considering AIonOS's capabilities:
{AIonOS_CAPABILITIES}

Extract up to two distinct challenges and provide corresponding AIonOS solutions. For each:
Clearly state a specific Challenge the company is facing in one short sentence.
Immediately follow it with a corresponding AIonOS Solution in one short sentence.

Format each entry exactly as:
Challenge: [One short sentence]
AIonOS Solution: [One short sentence]
URL: {url}

Challenge: [One short sentence]
AIonOS Solution: [One short sentence]
URL: {url}"""

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
            challenges = response.text.strip()
            if challenges:
                final_output.append(challenges)
    
    if not final_output:
        # Fallback to general knowledge if no content found
        prompt = f"""Based on your knowledge about {company_name}, provide two distinct entries. For each:
Clearly state a specific Challenge the company is facing in one short sentence.
Immediately follow it with a corresponding AIonOS Solution in one short sentence.

Format the output exactly as:
Challenge: [One short sentence]
AIonOS Solution: [One short sentence]

Challenge: [One short sentence]
AIonOS Solution: [One short sentence]"""
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(thread_pool, model.generate_content, prompt)
        final_output.append(response.text.strip())
    
    return {
        "summary": "\n\n".join(final_output),
        "urls": tried_urls
    }

async def generate_company_snapshot(company_name: str) -> dict:
    """Main function to generate company snapshot."""
    try:
        # Clean and validate company name
        company_name = company_name.strip()
        if not company_name:
            return {"error": "Please provide a valid company name."}
        
        # Remove any special characters that might cause format issues
        company_name = ''.join(c for c in company_name if c.isalnum() or c.isspace())
        
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Process all sections in parallel
            tasks = [
                get_executive_summary(client, company_name),
                get_key_facts(client, company_name),
                get_business_model(client, company_name),
                get_leadership(client, company_name),
                get_strategic_initiatives(client, company_name),
                get_data_maturity(client, company_name),
                get_partnerships(client, company_name),
                get_challenges_and_solutions(client, company_name)
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Structure the response
            snapshot = {
                "Company Snapshot": {
                    "Executive Summary": results[0],
                    "Key Facts": results[1],
                    "Business Model & Revenue Streams": results[2],
                    "Leadership": results[3]
                },
                "Initiatives": {
                    "Strategic Initiatives": results[4],
                    "Data Maturity & Initiatives": results[5],
                    "Partnerships": results[6]
                },
                "Challenges & AIonOS Opportunities": results[7]
            }
        
        end_time = time.time()
        print(f"Total processing time: {end_time - start_time:.2f} seconds")
        
        return {"snapshot": snapshot}
    except Exception as e:
        print(f"Error in generate_company_snapshot: {str(e)}")
        return {"error": str(e)}

async def main():
    """Main function to handle terminal input and display results."""
    print("\n=== Company Snapshot Generator ===\n")
    company_name = input("Enter company name: ").strip()
    
    if not company_name:
        print("Error: Please provide a valid company name.")
        return
    
    print(f"\n🔍 Generating snapshot for {company_name}...\n")
    
    try:
        result = await generate_company_snapshot(company_name)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return
            
        snapshot = result["snapshot"]
        
        # Print Company Snapshot
        print("\n📊 COMPANY SNAPSHOT")
        print("=" * 50)
        for section, data in snapshot["Company Snapshot"].items():
            print(f"\n{section}:")
            print("-" * len(section))
            print(data["summary"])
            if data["urls"]:
                print("\nSources:")
                for url in data["urls"]:
                    print(f"• {url}")
        
        # Print Initiatives
        print("\n\n🚀 INITIATIVES")
        print("=" * 50)
        for section, data in snapshot["Initiatives"].items():
            print(f"\n{section}:")
            print("-" * len(section))
            print(data["summary"])
            if data["urls"]:
                print("\nSources:")
                for url in data["urls"]:
                    print(f"• {url}")
        
        # Print Challenges & AIonOS Opportunities
        print("\n\n🎯 CHALLENGES & AIonOS OPPORTUNITIES")
        print("=" * 50)
        data = snapshot["Challenges & AIonOS Opportunities"]
        print(data["summary"])
        if data["urls"]:
            print("\nSources:")
            for url in data["urls"]:
                print(f"• {url}")
        
    except Exception as e:
        print(f"❌ An error occurred: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 