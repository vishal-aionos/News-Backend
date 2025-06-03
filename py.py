import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import time

# 🔐 API KEYS
SERPER_API_KEY = "768b1956ea4252916980afb7b0d7f31f8e5d2f37"
GEMINI_API_KEY = "AIzaSyAt_c0xgaXGg9H4oFX0YUqsQuhnV4gi7BY"
genai.configure(api_key=GEMINI_API_KEY)

# Constants
AIonOS_CAPABILITIES = (
    "AIonOS pioneers industry-specific Agentic AI solutions that autonomously solve "
    "complex business challenges while collaborating with human teams for optimal outcomes "
    "across travel, transport, hospitality, logistics, and telecom sectors."
)

# Step 1: SERPER Search
def search_company_challenges(company_name):
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY}
    payload = {"q": f"{company_name} latest business challenges"}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    results = response.json()
    return results["organic"][0]["link"] if results.get("organic") else None

# Step 2: Scrape Content
def extract_text_from_url(url):
    try:
        page = requests.get(url, timeout=10)
        soup = BeautifulSoup(page.text, "html.parser")
        paragraphs = soup.find_all("p")
        return "\n".join(p.get_text() for p in paragraphs).strip()
    except Exception as e:
        return f"Error extracting content: {e}"

# Step 3: Summarize Challenges
def summarize_challenges(text):
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = f"Summarize the main business challenges faced by this company. ensure the summary is in consise 3 to 5 bullet points and make sure points are relevant to the company challenges:\n\n{text[:5000]}"
    response = model.generate_content(prompt)
    return response.text.strip()

# Step 4: Generate AIonOS Solutions
def suggest_aionos_solutions(challenges_text):
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = (
        f"Given the following company challenges give them in consise 3 to 5 bullet points:\n\n"
        f"{challenges_text}\n\n"
        f"How can AIonOS help solve these challenges based on its capabilities give them in consise 3 to 5 bullet points:\n"
        f"{AIonOS_CAPABILITIES}\n\n"
        f"Respond in clear bullet points."
    )
    response = model.generate_content(prompt)
    return response.text.strip()

# Main Function
def main():
    company = input("Enter company name: ")
    print(f"\n🔍 Searching for {company} challenges...\n")
    
    url = search_company_challenges(company)
    if not url:
        print("❌ No relevant results found.")
        return

    print(f"🌐 Scraping content from: {url}\n")
    content = extract_text_from_url(url)
    if content.startswith("Error"):
        print(content)
        return

    print("🧠 Summarizing company challenges...\n")
    challenge_summary = summarize_challenges(content)
    print(f"📌 Company Challenges:\n{challenge_summary}\n")

    print("🤖 Mapping to AIonOS solutions...\n")
    aionos_response = suggest_aionos_solutions(challenge_summary)
    print(f"✅ How AIonOS Can Help:\n{aionos_response}")

# Run
if __name__ == "__main__":
    main()
