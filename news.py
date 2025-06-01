import requests
from newspaper import Article
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(
    title="News API",
    description="API to get company news and summaries",
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

# Function to search news using Serper
def search_news(company, page=1):
    url = "https://google.serper.dev/news"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    # Try different search queries to get more results
    queries = [
        f"{company} latest news",
        f"{company} company news",
        f"{company} investments news",
        f"{company} business news",
        f"{company} technology news"
    ]
    
    all_links = []
    for query in queries:
        payload = {"q": query}
        try:
            response = requests.post(url, headers=headers, json=payload)
            data = response.json()
            
            if "news" in data:
                company_words = company.lower().split()
                for item in data["news"]:
                    title = item.get("title", "").lower()
                    snippet = item.get("snippet", "").lower()
                    if any(word in title or word in snippet for word in company_words):
                        all_links.append(item["link"])
        except Exception:
            continue
            
    return all_links

# Scrape article using newspaper3k
def scrape_article(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        if len(article.text.strip()) > 500:
            return article.text[:20000]
    except Exception:
        return ""
    return ""

# Summarize using Gemini
def summarize(text, company):
    try:
        prompt = (
            f"Summarize the following article into 3–4 bullet points.remove intro and outro of the article in the summary.Only include information relevant to '{company}' and skip any generic or unrelated content:\n\n{text[:3000]}"
        )
        response = model.generate_content(prompt)
        summary = response.text.strip()
        if len(summary) < 30:
            return ""
        return summary
    except Exception:
        return ""

def news_theme_block_summary_with_gemini(article_summaries):
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
        return {"error": f"Theme block summary failed: {e}"}


@app.get("/news")
async def get_company_news(company: str):
    try:
        # Get news articles
        urls = search_news(company)
        if not urls:
            raise HTTPException(status_code=404, detail="No articles found")
        
        # Collect all valid summaries
        all_summaries = []
        seen_urls = set()
        articles_data = []
        search_attempts = 0
        max_attempts = 5  # Maximum number of search attempts

        while len(articles_data) < 10 and search_attempts < max_attempts:
            search_attempts += 1
            new_urls = [url for url in urls if url not in seen_urls]
            
            if not new_urls:
                continue

            for url in new_urls:
                if len(articles_data) >= 10:
                    break
                    
                seen_urls.add(url)
                text = scrape_article(url)
                
                if not text:
                    continue
                    
                summary = summarize(text, company)
                if not summary:
                    continue
                    
                # Clean up the summary
                cleaned_summary = ' '.join(summary.split())
                if cleaned_summary:
                    all_summaries.append(cleaned_summary)
                    articles_data.append({
                        "url": url,
                        "summary": cleaned_summary
                    })
        
        if not all_summaries:
            raise HTTPException(status_code=404, detail="No valid summaries could be generated")
            
        # Generate themes
        themes = news_theme_block_summary_with_gemini(all_summaries)
        
        # Structure the response
        response = {
            "company": company,
            "articles": articles_data,
            "themes": themes
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
