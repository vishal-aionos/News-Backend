from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import uvicorn
import re

# API Keys
TAVILY_API_KEY = "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"


app = FastAPI(
    title="News API",
    description="API to get company news and summaries",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def search_news(company):
    url = "https://api.tavily.com/search"
    # Properly format the company name for the search query
    formatted_company = company.strip()
    query = f'"{formatted_company}" latest news'  # Use quotes to keep the company name together
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "max_results": 10,
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
    GEMINI_API_KEY = "AIzaSyAgKdmYgZg-_jVt9wDqDgKPd2ow_OKGrgU"

    # Configure Gemini
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash-lite")
    try:
        prompt = (
    "Please summarize the following article in 3 to 5 concise bullet points. "
    "Focus only on content directly relevant to the company. "
    "strictly Avoid intro introductory or concluding statements, and exclude unrelated context:\n\n"
    + text[:5000]
)
        response = model.generate_content(prompt)
        summary = response.text.strip()
        return summary
    except Exception as e:
        return f"Summary failed: {e}"

def news_theme_block_summary_with_gemini(article_summaries):
    GEMINI_API_KEY = "AIzaSyAgKdmYgZg-_jVt9wDqDgKPd2ow_OKGrgU"

    # Configure Gemini
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")
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

def get_company_overview(summaries):
    try:
        if not summaries:
            raise ValueError("No summaries provided")
        cleaned_summaries = [' '.join(summary.split()) for summary in summaries]
        combined_summaries = "\n\n".join([f"Article {i+1}:\n{summary}" for i, summary in enumerate(cleaned_summaries)])

        GEMINI_API_KEY = "AIzaSyAgKdmYgZg-_jVt9wDqDgKPd2ow_OKGrgU"
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash-lite")

        prompt = (
            f"""You are a business analyst. Analyze the article summaries below and generate a structured company overview. Use all available information to provide a clear, concise summary. If any detail is missing take overall summary try to summarise accordingly"
            source: {combined_summaries}
            Instructions:
            Cover all the articles.
            Use 3 sentences per section.
            Return the Output Format (use exact section titles):
            {{
            Company Snapshot:{{
                Overview: Give a brief overview of the company.
                Executive Summary: What does the company do? What are its mission, vision, and value proposition?
                Key Facts: Founded year, headquarters, employee count, public/private status, stock info, and geographies.
                Business Model & Revenue Streams: Revenue sources and key products/services.
                Leadership: Key executives and board members.
                }}
             
            Initiatives:{{
            Strategic Initiatives: Top 1–3 year goals and how the company plans to achieve them.
            Data Maturity & Initiatives: Tech maturity, live/pilot/planned projects, tools, and AI/ML use cases.
            Partnerships: Key external partners and collaborations.
            }}
            }}"""
        )

        response = model.generate_content(prompt)
        import json
        import re
        overview_text = re.findall(r"```json\s*(\{.*?\})\s*```", response.text.strip(), re.DOTALL)[-1] 
        overview_text =json.loads(overview_text)
        print("Gemini Overview Response:\n", overview_text)


        return overview_text

    except Exception as e:
        return {
            "Company Snapshot": {
                "Overview": f"Error generating overview: {str(e)}",
                "Executive Summary": f"Error generating overview: {str(e)}",
                "Key Facts": f"Error generating overview: {str(e)}",
                "Business Model & Revenue Streams": f"Error generating overview: {str(e)}",
                "Leadership": f"Error generating overview: {str(e)}"
            },
            "Initiatives": {
                "Strategic Initiatives": f"Error generating overview: {str(e)}",
                "Data Maturity & Initiatives": f"Error generating overview: {str(e)}",
                "Partnerships": f"Error generating overview: {str(e)}"
            }
        }

@app.get("/news")
async def get_company_news(company: str):
    try:
        articles = search_news(company)
        
        if not articles:
            raise HTTPException(status_code=404, detail="No articles found")
        
        result = {
            "company": company,
            "articles": [],
            "themes": {},
            "company_overview": {}
        }
        
        # First collect all summaries
        all_summaries = []
        print(f"Found {len(articles)} articles for {company}")
        for idx, article in enumerate(articles):
            url = article["url"]
            print(f"\nProcessing Article {idx+1}: {url}")
            text = scrape_and_clean(url)
            
            if text.startswith("Failed"):
                print(f"  Scraping failed: {text}")
                summary = None # Ensure summary is None if scraping failed
            else:
                print(f"  Scraping successful. Text length: {len(text)}")
                if not text.strip():
                    print("  Scraped text is empty or only whitespace.")
                    summary = None
                else:
                    summary = summarize_with_gemini(text)
                    if summary is None or summary.startswith("Summary failed"):
                        print(f"  Summarization failed or returned error: {summary}")
                        summary = None # Ensure summary is None on failure
                    elif not summary.strip():
                         print("  Summarization returned empty or whitespace summary.")
                         summary = None
                    else:
                        # Clean up the summary: remove extra whitespace and normalize
                        cleaned_summary = ' '.join(summary.split())
                        if cleaned_summary:
                            print(f"  Summary generated successfully. Cleaned summary length: {len(cleaned_summary)}")
                            all_summaries.append(cleaned_summary)
                        else:
                            print("  Cleaned summary is empty.")
                            summary = None # Ensure summary is None if cleaned is empty

            article_data = {
                "url": url,
                "summary": summary
            }
            result["articles"].append(article_data)
        
        print(f"Total valid summaries collected: {len(all_summaries)}")
        # Verify we have summaries
        if not all_summaries:
            raise HTTPException(status_code=404, detail="No valid summaries could be generated")
            
        # Generate company overview with all summaries
        result["company_overview"] = get_company_overview(all_summaries)
        
        # Generate themes
        result["themes"] = news_theme_block_summary_with_gemini(all_summaries)
        
        return result
    
    except Exception as e:
        print(f"An error occurred in get_company_news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 