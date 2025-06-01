import requests
from newspaper import Article
import google.generativeai as genai

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

# Main logic
def main():
    company = input("Enter a company name: ").strip()
    company_words = company.lower().split()

    collected_summaries = []
    seen_urls = set()
    search_attempts = 0
    max_attempts = 5  # Maximum number of search attempts

    while len(collected_summaries) < 10 and search_attempts < max_attempts:
        search_attempts += 1
        urls = search_news(company)

        new_urls = [url for url in urls if url not in seen_urls]
        if not new_urls:
            continue

        for url in new_urls:
            seen_urls.add(url)
            text = scrape_article(url)

            if not text:
                continue

            if not any(word in text.lower() for word in company_words):
                continue

            summary = summarize(text, company)
            if not summary:  # Empty string means summary failed
                continue

            collected_summaries.append((url, summary))

            if len(collected_summaries) >= 10:
                break

    print(f"\nFound {len(collected_summaries)} relevant articles for '{company}':\n")
    for i, (url, summary) in enumerate(collected_summaries, 1):
        print(f"Article {i}: {url}\n{summary}\n")

if __name__ == "__main__":
    main()
