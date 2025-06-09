import asyncio
import httpx
from typing import Dict, List, Optional, Any
# Import necessary functions from py.py
from py import get_executive_summary, get_business_model, get_key_facts, get_leadership, get_challenges_and_solutions, AIonOS_CAPABILITIES, get_data_maturity, get_strategic_initiatives # Removed get_strategic_initiatives as it's not used here
import google.generativeai as genai # Assuming Gemini model is used for summarization

# Define a type hint for the battle card section data
BattleCardSectionData = Dict[str, Any]

# Assuming API key is accessible or passed in a config
# For now, let's assume it's defined elsewhere or will be added
# GENAI_API_KEY = "YOUR_API_KEY"
# genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash") # Using the same model as in py.py


async def get_what_we_do(client: httpx.AsyncClient, company_name: str) -> BattleCardSectionData:
    """Retrieves data for the 'WHAT WE DO' section by summarizing the executive summary."""
    try:
        # Get the executive summary using the client
        executive_summary_result = await get_executive_summary(client, company_name)
        
        summary_text = executive_summary_result.get("summary", "")
        
        if not summary_text:
            return {"summary": "Executive summary not available."}
            
        # Use Gemini to summarize what the company does
        prompt = f"""Summarize the following executive summary to describe what the company primarily does in one concise paragraph:

{summary_text}"""
        
        loop = asyncio.get_event_loop()
        # Execute the potentially blocking generate_content call in a thread pool
        summary_of_what_we_do = await loop.run_in_executor(None, model.generate_content, prompt)
        
        return {"summary": summary_of_what_we_do.text.strip()}
        
    except Exception as e:
        # Handle potential errors during fetching or summarization
        print(f"Error getting 'WHAT WE DO' data for {company_name}: {e}")
        return {"summary": "Error retrieving company description."}

async def get_company_offerings(client: httpx.AsyncClient, company_name: str) -> BattleCardSectionData:
    """Retrieves data for the 'COMPANY OFFERINGS' section by extracting products from the business model summary."""
    try:
        # Get the entire business model data
        business_model_result = await get_business_model(client, company_name)
        
        # Assuming the primary summary is under a key like 'summary'. Adjust if necessary.
        business_model_summary = business_model_result.get("summary", "")
        
        if not business_model_summary:
            return {"products": ["Business model summary not available to extract offerings."]}
        
        # Use Gemini to extract product names from the entire summary text
        prompt = f"""Analyze the following text describing the company's business model and extract the main products or services mentioned. List them one per line without any descriptions or extra text.
        if the summary doesnot have products then try to add the products according to the best knowledge without stating that the information was missing or inferred — just give the final answer 
{business_model_summary}"""
        
        loop = asyncio.get_event_loop()
        products_response = await loop.run_in_executor(None, model.generate_content, prompt)
        
        products_list = [line.strip() for line in products_response.text.strip().split('\n') if line.strip()]

        if not products_list:
             # If Gemini couldn't find products, return a message
             return {"products": ["No specific offerings identified from the business model."]}
        
        return {"products": products_list}
        
    except Exception as e:
        print(f"Error getting 'COMPANY OFFERINGS' data for {company_name}: {e}")
        return {"products": ["Error retrieving company offerings."]}

async def get_quick_facts(client: httpx.AsyncClient, company_name: str) -> BattleCardSectionData:
    """Retrieves all data from key facts."""
    try:
        # Get all key facts using the client
        key_facts_result = await get_key_facts(client, company_name)
        
        if not key_facts_result:
             return {"message": "Key facts information not available."}

        return key_facts_result
        
    except Exception as e:
        print(f"Error getting 'QUICK FACTS' data for {company_name}: {e}")
        return {"message": "Error retrieving quick facts."}

async def get_news_snapshot(client: httpx.AsyncClient, company_name: str, themes_data: Dict[str, str]) -> BattleCardSectionData:
    """Takes themes data, summarizes all points into a single list of concise points, and returns the summary."""
    try:
        # Check if themes_data is valid and contains any content worth summarizing
        # Consider data substantial if there's at least one theme with content other than "No major news"
        has_substantial_data = False
        if themes_data and isinstance(themes_data, dict):
            for theme, points in themes_data.items():
                if points and points.strip() != "No major news":
                    has_substantial_data = True
                    break
                    
        if not has_substantial_data:
             # Return a specific message if no substantial themes data is available
             return {"themes_summary": {"message": "No substantial news themes available to summarize."}, "articles": []}

        # Combine all themes and their points into a single text for summarization
        combined_themes_text = ""
        if isinstance(themes_data, dict):
            for theme, points in themes_data.items():
                 # Only include themes with actual content
                 if points and points.strip() != "No major news":
                      # Add theme name before points for context, even though the output prompt will ignore it
                      combined_themes_text += f"Theme: {theme}\nPoints: {points}\n\n"
        # If themes_data was unexpectedly not a dict but a string, use it directly
        elif isinstance(themes_data, str):
             combined_themes_text = themes_data
        
        # Double check if combined_themes_text is still empty after filtering
        if not combined_themes_text.strip():
             return {"themes_summary": {"message": "No substantial news themes available to summarize after processing."}, "articles": []}


        # Use Gemini to summarize the combined themes data into a single list of extremely concise bullet points
        prompt = f"""Analyze the following news themes and their key points. Provide a single list of extremely concise bullet points summarizing the most important takeaways from ALL the themes combined. Each bullet point should reflect one of the following categories: Partnerships, AI/Tech, Market Strategy, Expansion, Product/Fleet, Infrastructure/Investment.

Formatting Instructions:
Donot give intro or outro in the 
Begin each bullet point with the bullet mark • followed by a space.
Do not include any theme headings or subheadings in the output.
Keep each bullet point very short and to the point.
Ensure each bullet clearly reflects one of the six focus categories.
Here are the themes and points to analyze:{combined_themes_text}"""

        loop = asyncio.get_event_loop()
        summarized_response = await loop.run_in_executor(None, model.generate_content, prompt)
        
        # Split the response into points and clean them
        concise_points = [point.strip() for point in summarized_response.text.strip().split('\n') if point.strip()]

        if not concise_points:
            return {"themes_summary": {"message": "Could not generate concise summary from provided themes."}, "articles": []}
        
        # Return the concise summary points wrapped in the expected structure
        return {"themes_summary": {"summary_points": concise_points}}

    except Exception as e:
        print(f"Error summarizing themes in get_news_snapshot for {company_name}: {e}")
        return {"themes_summary": {"Error": f"Failed to summarize themes: {e}"}}

async def get_pic_overview(client: httpx.AsyncClient, company_name: str) -> BattleCardSectionData:
    """Retrieves data for the 'PIC OVERVIEW' section from leadership information."""
    return {"message": "PIC overview information currently unavailable."}

async def get_challenges_and_opportunities(client: httpx.AsyncClient, company_name: str, challenges_snapshot_data: Dict[str, Any]) -> BattleCardSectionData:
    """Takes challenges and AIonOS opportunities snapshot data, summarizes it into concise points, and returns the summary."""
    try:
        # Extract the summary text from the snapshot data
        # Based on the JSON, the summary is under the 'summary' key
        summary_text = challenges_snapshot_data.get("summary", "")
        
        if not summary_text or not summary_text.strip():
            return {"message": "Challenges and AIonOS opportunities summary not available."}
        
        # Use Gemini to summarize the text into concise bullet points
        prompt = f"""Summarize the following text into concise bullet points, each combining a company-specific challenge with how AIonOS can address it. Focus only on challenges faced by the company (not industry-wide or general ones), and pair each challenge directly with a solution enabled by AIonOS. Each bullet point should clearly state the challenge and its corresponding AIonOS capability.

Text to Summarize:
{summary_text}

Provide the output as a list of concise bullet points, one per line."""
        
        loop = asyncio.get_event_loop()
        summarized_response = await loop.run_in_executor(None, model.generate_content, prompt)
        
        # Split the response into points and clean them
        concise_points = [point.strip() for point in summarized_response.text.strip().split('\n') if point.strip()]

        if not concise_points:
            return {"message": "Could not generate concise summary for challenges and opportunities."}
        
        # Return the concise summary points
        return {"summary_points": concise_points}
        
    except Exception as e:
        print(f"Error summarizing challenges and opportunities for {company_name}: {e}")
        return {"message": f"Error retrieving or summarizing challenges and opportunities: {e}"}

async def get_industry_overview(client: httpx.AsyncClient, company_name: str) -> BattleCardSectionData:
    """Retrieves data for the 'INDUSTRY OVERVIEW' section."""
    # This function would typically fetch information about the industry the company is in.
    # We need a data source or a function in py.py that can provide this information.
    # For now, returning a placeholder.
    print(f"Function get_industry_overview called for {company_name}. Data source needed.")
    return {"summary": "Industry overview data needs to be implemented."}

async def get_data_maturity_and_initiatives(client: httpx.AsyncClient, company_name: str) -> BattleCardSectionData:
    """Retrieves and combines data maturity and strategic initiatives, summarizing into 4 concise points."""
    try:
        # Get both data maturity and strategic initiatives
        data_maturity_result = await get_data_maturity(client, company_name)
        strategic_initiatives_result = await get_strategic_initiatives(client, company_name)
        
        # Combine the text from both sources
        combined_text = ""
        if data_maturity_result and isinstance(data_maturity_result, dict):
            combined_text += data_maturity_result.get("summary", "")
        
        if strategic_initiatives_result and isinstance(strategic_initiatives_result, dict):
            combined_text += "\n" + strategic_initiatives_result.get("summary", "")
        
        if not combined_text.strip():
            return {"points": ["No data maturity or initiatives information available."]}
        
        # Use Gemini to summarize into 4 concise points
        prompt = f"""Summarize the following information about data maturity and strategic initiatives into exactly 4 concise points. Each point should be 4-5 words and focus on key capabilities or initiatives. Format as a simple list, one point per line.
donot give intro or outro in the output.
{combined_text}

Example format:
Cloud Data Pipeline connector
Data Ingestion Accelerator
AutoML Framework
Data Science "Cookbook"

Provide exactly 4 points, one per line."""
        
        loop = asyncio.get_event_loop()
        summary_response = await loop.run_in_executor(None, model.generate_content, prompt)
        
        # Split the response into points and clean them
        points = [point.strip() for point in summary_response.text.strip().split('\n') if point.strip()]
        
        # Ensure we have exactly 4 points
        if len(points) > 4:
            points = points[:4]
        elif len(points) < 4:
            points.extend(["No additional information available."] * (4 - len(points)))
        
        return {"points": points}
        
    except Exception as e:
        print(f"Error getting data maturity and initiatives for {company_name}: {e}")
        return {"points": ["Error retrieving data maturity and initiatives."] * 4}

async def generate_battle_card(company_name: str) -> Dict[str, BattleCardSectionData]:
    """Generates the complete battle card data for a given company."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        what_we_do_data = await get_what_we_do(client, company_name)
        company_offerings_data = await get_company_offerings(client, company_name)
        quick_facts_data = await get_quick_facts(client, company_name)
        news_snapshot_data = await get_news_snapshot(client, company_name, {})
        pic_overview_data = await get_pic_overview(client, company_name)
        challenges_data = await get_challenges_and_opportunities(client, company_name, {})
        industry_overview_data = await get_industry_overview(client, company_name)
        data_maturity_data = await get_data_maturity_and_initiatives(client, company_name)
        
        battle_card_data = {
            "WHAT WE DO": what_we_do_data,
            "COMPANY OFFERINGS": company_offerings_data,
            "QUICK FACTS": quick_facts_data,
            "NEWS SNAPSHOT": news_snapshot_data,
            "PIC OVERVIEW": pic_overview_data,
            "CHALLENGES & AIONOS OPPORTUNITIES": challenges_data,
            "INDUSTRY OVERVIEW": industry_overview_data,
            "DATA MATURITY & INITIATIVES": data_maturity_data,
        }
        
        return battle_card_data 