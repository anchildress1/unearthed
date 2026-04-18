"""One-shot model comparison for Gemini prose quality. Not a test suite — delete after use."""

import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from google import genai  # noqa: E402

api_key = os.environ.get("GEMINI_API_KEY", "")
if not api_key:
    raise SystemExit("GEMINI_API_KEY not set")

client = genai.Client(api_key=api_key)

prompt_template = (Path(__file__).parent.parent / "assets" / "gemini_prompt.txt").read_text()
prompt = prompt_template.format(
    mine_name="Black Thunder Mine",
    mine_operator="Arch Resources",
    mine_county="Campbell",
    mine_state="Wyoming",
    mine_type="Surface",
    plant_name="Labadie Energy Center",
    plant_operator="Ameren Missouri",
    tons_latest_year="4,200,000",
    tons_year="2023",
    subregion_id="SRMW",
)

candidates = [
    ("gemini-2.5-flash", "fast + cheap — baseline"),
    ("gemini-2.5-pro", "most capable — quality ceiling"),
    ("gemini-3-flash-preview", "Gemini 3 flash preview"),
    ("gemini-3-pro-preview", "Gemini 3 pro preview"),
]

for model, label in candidates:
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"MODEL: {model} ({label})")
    print(sep)
    t0 = time.time()
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        elapsed = time.time() - t0
        print(f"Latency: {elapsed:.2f}s")
        print()
        print(response.text.strip())
    except Exception as exc:
        print(f"ERROR: {exc}")
