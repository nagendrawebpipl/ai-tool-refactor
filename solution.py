#!/usr/bin/env python3
import json
import os
import sys
import re
import time
from pathlib import Path
import anthropic

def build_prompt(item):
    filename = item["filename"]
    legacy_code = item["legacy_code"]
    issues = "\n".join(f"  - {i}" for i in item["issues"])
    goals = item["refactoring_goals"]
    return f"""You are an expert Python refactoring assistant.

Refactor the legacy Python file below. Address every listed issue and honour the refactoring goals.

## File: {filename}
## Issues to fix:
{issues}
## Refactoring goals:
{goals}

## Legacy code:
\\\python
{legacy_code}
\\\

## Instructions
Produce exactly three refactored modules that together replace the original file.
Name them based on their concern:
  1. <stem>_io.py     - file I/O (load / save), uses pathlib.Path, context managers, type hints
  2. <stem>_auth.py   - authorisation (token check), raises typed exceptions, no globals
  3. <stem>_handler.py- business logic / request handling; imports from the two modules above;
                        uses dependency injection (pass cache/db as arguments), flat conditionals

Where stem is the filename without the .py extension and without trailing _<digit>.

Respond ONLY with a JSON object (no markdown fences, no extra text) with this exact shape:
{{
  "modules": [
    {{"filename": "<stem>_io.py",      "code": "<full source>"}},
    {{"filename": "<stem>_auth.py",    "code": "<full source>"}},
    {{"filename": "<stem>_handler.py", "code": "<full source>"}}
  ],
  "summary": "<one-sentence description of changes made>"
}}
"""

def call_claude(client, prompt, retries=3):
    for attempt in range(retries):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            raw = re.sub(r"^\\(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*\\$", "", raw)
            return json.loads(raw)
        except (json.JSONDecodeError, anthropic.APIError) as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Claude call failed after {retries} attempts: {exc}") from exc

def main():
    test_inputs_path = Path("test_inputs.json")
    results_path = Path("results.json")

    if not test_inputs_path.exists():
        print(f"ERROR: {test_inputs_path} not found", file=sys.stderr)
        sys.exit(1)

    test_inputs = json.loads(test_inputs_path.read_text())
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    results = []
    total = len(test_inputs)

    for idx, item in enumerate(test_inputs, 1):
        item_id = item["id"]
        filename = item["filename"]
        print(f"[{idx}/{total}] Refactoring {filename} ({item_id}) ...")
        try:
            prompt = build_prompt(item)
            claude_output = call_claude(client, prompt)
            results.append({
                "id": item_id,
                "output": {
                    "original_filename": filename,
                    "refactored_modules": claude_output["modules"],
                    "summary": claude_output.get("summary", ""),
                    "issues_addressed": item["issues"],
                },
            })
            print(f"  Done - {len(claude_output['modules'])} modules generated")
        except Exception as exc:
            print(f"  Error: {exc}", file=sys.stderr)
            results.append({
                "id": item_id,
                "output": {
                    "original_filename": filename,
                    "refactored_modules": [],
                    "summary": f"ERROR: {exc}",
                    "issues_addressed": [],
                },
            })

    results_path.write_text(json.dumps(results, indent=2))
    print(f"\nDone - wrote {len(results)} results to {results_path}")

if __name__ == "__main__":
    main()
