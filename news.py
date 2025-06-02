import requests
from newspaper import Article
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from company_snapshot import generate_company_snapshot

app = FastAPI(
    title="News API",
    description="API to get company news, summaries, and company snapshot",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Keys
SERPER_API_KEY = "768b1956ea4252916980afb7b0d7f31f8e5d2f37"
GEMINI_API_KEY = "AIzaSyAgKdmYgZg-_jVt9wDqDgKPd2ow_OKGrgU"

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-lite")

async def search_news_async(client: httpx.AsyncClient, query: str) -> List[str]:
    url = "https://google.serper.dev/news"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"q": query}
    
    try:
        response = await client.post(url, headers=headers, json=payload)
        data = response.json()
        
        if "news" in data:
            # Filter out irrelevant results
            company_words = query.split()[0].lower()  # Get company name
            relevant_links = []
            seen_titles = set()
            
            for item in data["news"]:
                title = item.get("title", "").lower()
                snippet = item.get("snippet", "").lower()
                
                # Skip if we've seen a similar title
                if any(title in seen_title or seen_title in title for seen_title in seen_titles):
                    continue
                    
                # Check if the content is relevant
                if (company_words in title or company_words in snippet) and \
                   not any(word in title.lower() for word in ["stock", "share", "price", "trading", "market"]):
                    relevant_links.append(item["link"])
                    seen_titles.add(title)
            
            return relevant_links
    except Exception as e:
        print(f"Search error: {str(e)}")
        return []
    return []

async def search_news(company: str) -> List[str]:
    # More focused search queries
    queries = [
        f"{company} latest news 2025",
        f"{company} recent company announcements June 2025",
        f"{company} latest press releases 2025",
        f"{company} new partnerships 2025",
        f"{company} technology industry news 2025",

    ]
    
    async with httpx.AsyncClient() as client:
        tasks = [search_news_async(client, query) for query in queries]
        results = await asyncio.gather(*tasks)
        
    # Flatten results and remove duplicates
    all_links = list(set([link for sublist in results for link in sublist]))
    return all_links[:20]  # Limit to 20 URLs as suggested

async def scrape_article_async(client: httpx.AsyncClient, url: str) -> str:
    try:
        response = await client.get(url, timeout=10.0)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
            element.decompose()
            
        # Get main content with better targeting
        article_text = ""
        
        # Try to find the main article content
        main_content = soup.find('article') or soup.find('main') or soup.find('div', class_=['content', 'article', 'story'])
        if main_content:
            article_text = ' '.join([p.get_text().strip() for p in main_content.find_all(['p', 'h1', 'h2', 'h3'])])
        else:
            # Fallback to all paragraphs if no main content found
            article_text = ' '.join([p.get_text().strip() for p in soup.find_all('p')])
        
        # Clean up the text
        article_text = ' '.join(article_text.split())
        
        if len(article_text) > 500:
            return article_text[:20000]
    except Exception as e:
        print(f"Scraping error for {url}: {str(e)}")
        return ""
    return ""

async def scrape_articles(urls: List[str]) -> List[Dict[str, str]]:
    async with httpx.AsyncClient() as client:
        tasks = [scrape_article_async(client, url) for url in urls]
        texts = await asyncio.gather(*tasks)
        
    return [{"url": url, "text": text} for url, text in zip(urls, texts) if text]

def summarize_sync(text: str, company: str) -> str:
    try:
        # Check if the text contains enough relevant content
        company_words = company.lower().split()
        text_lower = text.lower()
        
        # Count occurrences of company name and related terms
        relevance_score = sum(text_lower.count(word) for word in company_words)
        
        if relevance_score < 3:  # Minimum threshold for relevance
            return ""
            
        prompt = (
            f"Summarize the following article into 3–4 bullet points. Focus only on concrete news and developments about {company}. "
            f"Exclude any generic information, stock prices, or market analysis. "
            f"Only include specific facts, numbers, and announcements:\n\n{text[:3000]}"
        )
        response = model.generate_content(prompt)
        summary = response.text.strip()
        
        # Validate summary quality
        if len(summary) < 50 or "no information" in summary.lower() or "doesn't contain" in summary.lower():
            return ""
            
        return ' '.join(summary.split())  # Clean up whitespace
    except Exception as e:
        print(f"Summarization error: {str(e)}")
        return ""

async def summarize_articles(articles: List[Dict[str, str]], company: str) -> List[Dict[str, str]]:
    # Process articles in batches to avoid overwhelming the API
    batch_size = 5
    all_summaries = []
    
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        # Run summarization in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, summarize_sync, article["text"], company)
            for article in batch
        ]
        summaries = await asyncio.gather(*tasks)
        
        for article, summary in zip(batch, summaries):
            if summary:
                all_summaries.append({
                    "url": article["url"],
                    "summary": summary
                })
                
        # If we have enough summaries, stop processing
        if len(all_summaries) >= 10:
            break
            
    return all_summaries[:10]  # Ensure we return at most 10 summaries

def generate_themes_sync(article_summaries: List[str]) -> Dict[str, str]:
    try:
        prompt = (
            "Given the following news article summaries, organize the key points under these themes: "
            "ensure content inside each theme is relevant to the theme and the company."
            "For each theme, provide 2 or 3 concise points (comma-separated, or as a short paragraph). "
            "If there is no news for a theme, write 'No major news'. "
            "Format the output as follows (do not use markdown or bullet points):\n"
            "News\n"
            "1) Partnerships: ...\n"
            "2) AI/Tech: ...\n"
            "3) Market Strategy: ...\n"
            "4) Expansion: ...\n"
            "5) Product/Fleet: ...\n"
            "6) Infra/Invest: ...\n\n"
            "Here are the summaries:\n\n" + "\n\n".join(article_summaries)
        )
        response = model.generate_content(prompt)
        theme_text = response.text.strip()
        
        # Parse the theme text into a structured format
        themes = {}
        current_theme = None
        
        for line in theme_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith(('1)', '2)', '3)', '4)', '5)', '6)')):
                theme_name = line.split(':', 1)[0].split(')')[1].strip()
                content = line.split(':', 1)[1].strip() if ':' in line else ''
                themes[theme_name] = content
                
        return themes
    except Exception as e:
        print(f"Theme generation error: {str(e)}")
        return {
            "Partnerships": "No major news",
            "AI/Tech": "No major news",
            "Market Strategy": "No major news",
            "Expansion": "No major news",
            "Product/Fleet": "No major news",
            "Infra/Invest": "No major news"
        }

@app.get("/news")
async def get_company_news(company: str):
    try:
        # Get news articles
        urls = await search_news(company)
        if not urls:
            raise HTTPException(status_code=404, detail="No articles found")
        
        # Scrape articles concurrently
        articles = await scrape_articles(urls)
        if not articles:
            raise HTTPException(status_code=404, detail="No valid articles could be scraped")
            
        # Summarize articles concurrently
        articles_data = await summarize_articles(articles, company)
        if not articles_data:
            raise HTTPException(status_code=404, detail="No valid summaries could be generated")
            
        # Generate themes
        all_summaries = [article["summary"] for article in articles_data]
        loop = asyncio.get_event_loop()
        themes = await loop.run_in_executor(None, generate_themes_sync, all_summaries)
        
        # Generate company snapshot
        snapshot_result = await generate_company_snapshot(company)
        
        # Structure the response
        response = {
            "company": company,
            "articles": articles_data,
            "themes": themes,
            "company_snapshot": snapshot_result.get("snapshot", "No snapshot available")
        }
        
        return JSONResponse(
            content=response,
            status_code=200,
            headers={"Content-Type": "application/json"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("news:app", host="0.0.0.0", port=8000, reload=True)
