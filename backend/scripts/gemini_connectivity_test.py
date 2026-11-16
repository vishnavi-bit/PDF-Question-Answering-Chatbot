"""
Standalone Gemini connectivity test (no PDFs, no retrieval, no database).

It sends ONE tiny prompt, "Reply with exactly OK.", and reports the result and
how long it took. Use it to tell whether Gemini itself is slow or reachable,
separately from the RAG pipeline.

Run from the backend folder:
    .\\.venv\\Scripts\\python.exe scripts\\gemini_connectivity_test.py
    .\\.venv\\Scripts\\python.exe scripts\\gemini_connectivity_test.py --model gemini-2.5-flash-lite
    .\\.venv\\Scripts\\python.exe scripts\\gemini_connectivity_test.py --timeout 60

The API key is read from backend/.env. It is never printed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from google import genai  # noqa: E402
from google.genai import errors, types  # noqa: E402

from app.core.config import get_settings  # noqa: E402

PROMPT = "Reply with exactly OK."


def main() -> int:
    parser = argparse.ArgumentParser(description="Send 'Reply with exactly OK.' to Gemini.")
    parser.add_argument("--model", default=None, help="Model to test (default: GEMINI_MODEL from .env)")
    parser.add_argument("--timeout", type=float, default=60.0, help="Seconds before giving up (default 60)")
    parser.add_argument(
        "--thinking-level",
        default=None,
        choices=["minimal", "low", "medium", "high"],
        help="Optional thinking level. Omit to use the model default.",
    )
    parser.add_argument("--max-output-tokens", type=int, default=256, help="Output limit (thinking counts too)")
    args = parser.parse_args()

    settings = get_settings()
    model = args.model or settings.gemini_model
    if not settings.gemini_api_key.strip():
        print("RESULT: NO KEY. Set GEMINI_API_KEY in backend/.env first.")
        return 2

    print(f"Model:   {model}")
    print(f"Timeout: {args.timeout} s (SDK-level, one attempt, no retries)")
    print(f"Prompt:  {PROMPT!r}")
    print(f"Thinking level: {args.thinking_level or 'model default'}")

    # One attempt only, so the measured time is the real single-request time.
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=int(args.timeout * 1000)),
    )
    started = time.monotonic()
    try:
        response = client.models.generate_content(
            model=model,
            contents=PROMPT,
            config=types.GenerateContentConfig(
                max_output_tokens=args.max_output_tokens,
                temperature=0.0,
                thinking_config=(
                    types.ThinkingConfig(thinking_level=args.thinking_level.upper())
                    if args.thinking_level
                    else None
                ),
            ),
        )
    except errors.APIError as exc:
        elapsed = time.monotonic() - started
        print(f"Duration: {elapsed:.1f} s")
        print(f"RESULT: FAILED with HTTP {exc.code} ({exc.status}). Provider message: {(exc.message or '')[:200]}")
        return 1
    except Exception as exc:  # network or timeout problems
        elapsed = time.monotonic() - started
        print(f"Duration: {elapsed:.1f} s")
        print(f"RESULT: FAILED with {type(exc).__name__}: {str(exc)[:200]}")
        return 1

    elapsed = time.monotonic() - started
    text = (response.text or "").strip()
    usage = getattr(response, "usage_metadata", None)
    print(f"Duration: {elapsed:.1f} s")
    print(f"Reply:   {text!r}")
    if usage is not None:
        print(
            f"Tokens:  prompt={getattr(usage, 'prompt_token_count', None)} "
            f"output={getattr(usage, 'candidates_token_count', None)} "
            f"thoughts={getattr(usage, 'thoughts_token_count', None)}"
        )
    if text == "OK":
        print("RESULT: SUCCESS (model replied exactly OK)")
        return 0
    print("RESULT: REACHED GEMINI but the reply was not exactly 'OK'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
