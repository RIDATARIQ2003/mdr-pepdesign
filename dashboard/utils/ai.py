# utils/ai.py
# Gemini API natural language interface for PepDesign
# Handles user prompts and returns structured responses
#
# Uses the `google-genai` SDK (the older `google-generativeai` package
# was deprecated). Install with:
#     pip install google-genai python-dotenv

from google import genai
from google.genai import types
import json
import os

try:
    # Loads GEMINI_API_KEY from a .env file next to app.py, if present.
    # This is the #1 fix for "the key works in my terminal but not in
    # Streamlit" — env vars set with `set` in one terminal session don't
    # carry over to a different terminal / IDE / shortcut that launches
    # Streamlit. A .env file makes the key available regardless of how
    # you launch the app.
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv is optional - falls back to whatever is already in the
    # environment if it's not installed.
    pass

# ── SETTINGS ─────────────────────────────────────────────────
# gemini-2.5-flash is on Google's free tier as of mid-2026, but Google
# has announced an Oct 16 2026 shutdown for it, and some accounts are
# already seeing early "model no longer available" errors ahead of that
# date. If you start seeing errors mentioning "no longer available" or
# "404", swap this string for "gemini-3-flash-preview" (also free tier)
# and everything else below keeps working unchanged.
GEMINI_MODEL = "gemini-2.5-flash"
MAX_TOKENS   = 2048  # bumped from 1000 - the old limit could truncate
                       # the JSON response mid-object, which produced
                       # unparsable output that looked like a crash.

# ── GET API KEY FROM ENVIRONMENT ─────────────────────────────
# Get a free key (no credit card required) from:
# https://aistudio.google.com/apikey
#
# EASIEST SETUP: create a file named `.env` in the same folder as
# app.py (dashboard/.env) containing one line:
#     GEMINI_API_KEY=your_key_here
# This works no matter which terminal/IDE you launch Streamlit from.
API_KEY = os.environ.get("GEMINI_API_KEY", "")

SYSTEM_PROMPT = """You are PepDesign AI — an expert assistant
for a computational peptide inhibitor design pipeline targeting
drug-resistant bacterial proteins.

The pipeline designs novel peptide inhibitors against EmrE
(UniProt P23895 / PDB: 3B5D), a multidrug resistance (MDR) efflux
pump in E. coli. Key facts:
- Binding site: E14 residue (proton-binding site, dimer interface)
- Best candidate: pep_0304 (KWCFVCYRGICYRRCG), delta-G -12.10 kcal/mol
- 341 peptides generated, 311 passed ML pre-screening, 282 docked
- 180 peptides met the -8.0 kcal/mol threshold; 20 top-tier candidates
  sent for AlphaFold-Multimer validation
- ML model: Random Forest classifier, AUC 0.87, trained on 3,913
  antimicrobial peptides from DRAMP
- Tools: RFdiffusion, ProteinMPNN, ESMFold, AutoDock Vina,
  AlphaFold-Multimer

When the user asks a question, respond ONLY with the JSON object
described by the response schema. Keep "answer" scientific but
accessible, and be specific about numbers. If a question is outside
the scope of this project, set "action" to "none" and answer briefly
and honestly rather than guessing."""

# Explicit schema - this is the biggest reliability upgrade over just
# using response_mime_type alone. Gemini is much less likely to drift
# from the exact shape app.py expects when the schema is pinned here
# instead of only described in English inside the system prompt.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "action": {
            "type": "string",
            "enum": ["filter", "view", "explain", "design", "none"],
        },
        "filter_params": {"type": "object"},
    },
    "required": ["answer", "steps", "action", "filter_params"],
}

DEFAULT_RESPONSE = {
    "answer": "",
    "steps": [],
    "action": "none",
    "filter_params": {},
}


def ask_pepdesign(user_prompt: str, context: dict | None = None) -> dict:
    """
    Send a prompt to Gemini and get a structured response.

    Parameters:
    -----------
    user_prompt : str  — what the user typed
    context     : dict — current app state (selected peptide etc.)

    Returns:
    --------
    dict with keys: answer, steps, action, filter_params
    """
    context = context or {}  # avoid the mutable-default-argument trap

    if not API_KEY:
        return {
            "answer": "API key not set. Add GEMINI_API_KEY to your environment or a .env file.",
            "steps": [
                "Get a free key at aistudio.google.com/apikey",
                "Create a .env file next to app.py with: GEMINI_API_KEY=your_key_here",
                "Restart Streamlit completely (not just rerun)",
                "Try again",
            ],
            "action": "none",
            "filter_params": {},
        }

    try:
        client = genai.Client(api_key=API_KEY)

        full_prompt = user_prompt
        if context:
            full_prompt += f"\n\nCurrent context: {json.dumps(context)}"

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=MAX_TOKENS,
                response_mime_type="application/json",
                response_json_schema=RESPONSE_SCHEMA,
            ),
        )

        # Guard against blocked/empty responses before touching .text -
        # some SDK versions raise on .text when a response was blocked
        # by safety filters rather than returning an empty string.
        text = getattr(response, "text", None)
        if not text:
            reason = None
            try:
                reason = response.candidates[0].finish_reason
            except Exception:
                pass
            return {
                **DEFAULT_RESPONSE,
                "answer": f"Gemini returned no usable content (finish_reason={reason}). Try rephrasing your question.",
            }

        try:
            parsed = json.loads(text.strip())
            # Fill in any keys the model might have dropped so app.py
            # never has to defensively check for missing keys.
            return {**DEFAULT_RESPONSE, **parsed}
        except (json.JSONDecodeError, TypeError):
            return {
                **DEFAULT_RESPONSE,
                "answer": text,
                "steps": ["(Response was not valid JSON - shown as raw text. "
                           "This usually means the reply got cut off - try a shorter question.)"],
            }

    except Exception as e:
        # Surface the real exception type/message so you can actually
        # diagnose it, instead of a generic "Error: ..." string.
        return {
            **DEFAULT_RESPONSE,
            "answer": f"Error calling Gemini ({type(e).__name__}): {e}",
            "steps": [str(e)],
        }


def get_api_key_instructions():
    """Returns instructions for setting up the API key."""
    return """
    To enable AI prompts:
    1. Get a free Gemini API key from aistudio.google.com/apikey
       (no credit card required)
    2. Create a file named .env in the dashboard/ folder (next to app.py)
       containing one line:
           GEMINI_API_KEY=your_key_here
    3. pip install python-dotenv  (if not already installed)
    4. Run: streamlit run dashboard/app.py
    """


if __name__ == "__main__":
    # Standalone test harness - run this file directly with
    # `python ai.py` to see the exact raw error without Streamlit
    # in the way. This is the fastest way to tell whether the
    # problem is the API key, the model name, or something else.
    print(f"API_KEY loaded: {'yes (' + API_KEY[:6] + '...)' if API_KEY else 'NO - not found in environment or .env'}")
    print(f"Model: {GEMINI_MODEL}")
    print("Sending test prompt...\n")
    result = ask_pepdesign("What was the best candidate peptide and its binding affinity?")
    print(json.dumps(result, indent=2))
