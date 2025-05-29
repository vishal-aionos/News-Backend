from fastapi import FastAPI, HTTPException
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import uvicorn

# API Keys
TAVILY_API_KEY = "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"
GEMINI_API_KEY = "AIzaSyAgKdmYgZg-_jVt9wDqDgKPd2ow_OKGrgU"

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-exp-image-generation")

app = FastAPI(
    title="News API",
    description="API to get company news and summaries",
    version="1.0.0"
)

def search_news(company):
    url = "https://api.tavily.com/search"
    query = f"{company} latest news"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "max_results": 5,
        "include_answer": False
    }
    response = requests.post(url, json=payload)
    return response.json().get("results", [])

def scrape_and_clean(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        return f"Failed to fetch content: {str(e)}"
 
    soup = BeautifulSoup(response.text, 'html.parser')
    text_elements = soup.find_all(['p', 'div', 'span', 'li'])
 
    full_text = "\n".join(
        text for el in text_elements
        if (text := el.get_text(strip=True)) and len(text) > 40
    )
    return full_text[:20000]

def summarize_with_gemini(text):
    try:
        prompt = (
            "Summarize the following article in a concise paragraph:\n\n" +
            text[:7000]
        )
        response = model.generate_content(prompt)
        summary = response.text.strip()
        return summary
    except Exception as e:
        return f"Summary failed: {e}"

def news_theme_block_summary_with_gemini(article_summaries):
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
    try:
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
        articles = search_news(company)
        
        if not articles:
            raise HTTPException(status_code=404, detail="No articles found")
        
        result = {
            "company": company,
            "articles": [],
            "themes": {}
        }
        
        for article in articles:
            url = article["url"]
            text = scrape_and_clean(url)
            
            article_data = {
                "url": url,
                "summary": summarize_with_gemini(text) if not text.startswith("Failed") else None
            }
            result["articles"].append(article_data)
        
        # Theme-wise summary
        all_summaries = [article["summary"] for article in result["articles"] if article["summary"]]
        result["themes"] = news_theme_block_summary_with_gemini(all_summaries)
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 