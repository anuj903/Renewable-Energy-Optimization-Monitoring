import os
import json
import re

# --- 1. PYTHON 3.9 COMPATIBILITY PATCH ---
try:
    import importlib.metadata
    if not hasattr(importlib.metadata, 'packages_distributions'):
        import importlib_metadata
        importlib.metadata.packages_distributions = importlib_metadata.packages_distributions
except ImportError:
    pass 

# --- 2. SETUP GOOGLE AI ---
HAS_GEMINI = False
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except Exception as e:
    print(f"⚠️ Google AI Library Error: {e}")

# API key is now read from environment for security (e.g. Railway: GEMINI_API_KEY)
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()


def get_dynamic_model():
    """
    Dynamically finds a working model instead of hardcoding names.
    Prioritizes 'flash', then 'gemini-1.5', then 'pro'.
    """
    if not HAS_GEMINI:
        return None

    if not API_KEY:
        print("⚠️ GEMINI_API_KEY not set. AI scheduling disabled.")
        return None

    try:
        genai.configure(api_key=API_KEY)
        
        # Get list of all available models
        all_models = list(genai.list_models())
        
        # Filter for models that support 'generateContent'
        valid_models = [m for m in all_models if 'generateContent' in m.supported_generation_methods]
        
        print(f"🔎 Found {len(valid_models)} valid AI models.")
        
        # Strategy 1: Look for 'flash' (Fastest)
        for m in valid_models:
            if 'flash' in m.name:
                print(f"✅ Selected Model: {m.name}")
                return genai.GenerativeModel(m.name)
                
        # Strategy 2: Look for 'gemini-1.5' (Newest Standard)
        for m in valid_models:
            if 'gemini-1.5' in m.name:
                print(f"✅ Selected Model: {m.name}")
                return genai.GenerativeModel(m.name)

        # Strategy 3: Look for 'pro' (Legacy)
        for m in valid_models:
            if 'pro' in m.name:
                print(f"✅ Selected Model: {m.name}")
                return genai.GenerativeModel(m.name)

        # Strategy 4: Desperation - Just pick the first one
        if valid_models:
            print(f"⚠️ specific model not found. Using generic: {valid_models[0].name}")
            return genai.GenerativeModel(valid_models[0].name)
            
        print("❌ No valid generative models found for this API Key.")
        return None

    except Exception as e:
        print(f"❌ Model Discovery Error: {e}")
        return None

# Initialize model once
ai_model = get_dynamic_model()

def get_optimized_schedule(slots_json, backlog_list, target_date):
    if not ai_model:
        return {"Schedule": [], "Insights": "AI Model unavailable."}

    print(f"🔹 Sending to AI ({ai_model.model_name}): {len(backlog_list)} jobs...")

    prompt = f"""
    Act as an Industrial Scheduler for a solar-powered foundry.
    TARGET DATE: {target_date}
    SCHEDULING WINDOW: 09:00 to 16:00 (all tasks must START and END within this window).

    INPUT DATA:
    1. FREE ENERGY SLOTS (kW available per hour):
    {slots_json}

    2. JOB BACKLOG (jobs to schedule):
    {json.dumps(backlog_list)}

    SCHEDULING RULES:
    - All tasks MUST start at or after 09:00 and finish by 16:00.
    - Prioritise jobs in order: High → Med → Low. Schedule High priority jobs first.
    - If a job requires more power (kW) than the available slot, DO NOT schedule it.
    - If a job has Qty > 1, create ONE separate schedule entry per unit.
      Each unit MUST be scheduled SEQUENTIALLY on the same Resource
      (unit 2 starts only after unit 1 ends, unit 3 starts after unit 2 ends, etc.).
    - No two tasks may occupy the exact same time slot on the same Resource.
    - Use human-readable task names (replace underscores with spaces).

    OUTPUT FORMAT (Strict JSON only, no markdown):
    {{
      "Schedule": [
        {{
          "Task": "Human readable job name (spaces, not underscores)",
          "ID": "Unique ID (e.g. Job_1)",
          "Start": "YYYY-MM-DD HH:MM:SS",
          "End": "YYYY-MM-DD HH:MM:SS",
          "Status": "Scheduled",
          "Resource": "Line 1",
          "Priority": "High | Med | Low"
        }}
      ],
      "Insights": "• Point 1: Summary of schedule efficiency.\\n• Point 2: Key trade-off made.\\n• Point 3: Suggestion for further optimisation."
    }}
    """
    
    try:
        response = ai_model.generate_content(prompt)
        raw_text = response.text
        
        # Robust Parsing (Regex)
        json_match = re.search(r'\{.*\}', raw_text.replace("```json", "").replace("```", ""), re.DOTALL)
        
        if json_match:
            clean_json = json_match.group(0)
            print("✅ AI Success!")
            return json.loads(clean_json)
        else:
            print("❌ AI returned text but no JSON found.")
            return {"Schedule": [], "Insights": "AI Parsing Failed."}

    except Exception as e:
        print(f"❌ Generation Error: {e}")
        return {"Schedule": [], "Insights": "AI Error. Check Terminal."}