#!/usr/bin/env python3
import json
import os
import re
import sys
import time
from pathlib import Path
import anthropic

TEST_INPUTS_PATH = Path(os.environ.get("TEST_INPUTS_PATH", "test_inputs.json"))
RESULTS_PATH     = Path(os.environ.get("RESULTS_PATH",     "results.json"))

def build_prompt(item):
    filename = item["filename"]
    legacy_code = item["legacy_code"]
    issues = "\n".join(f"  - {i}" for i in item["issues"])
    goals = item["refactoring_goals"]
    return (
        "You are an expert Python refactoring assistant.\n"
        "Refactor the legacy Python file below. Address every listed issue and honour the refactoring goals.\n\n"
        f"## File: {filename}\n"
        f"## Issues to fix:\n{issues}\n"
        f"## Refactoring goals:\n{goals}\n\n"
        "## Legacy code:\n"
        f"{legacy_code}\n\n"
        "Produce exactly three refactored modules:\n"
        "1. <stem>_io.py - file I/O, pathlib, context managers, type hints\n"
        "2. <stem>_auth.py - authorisation, typed exceptions, no globals\n"
        "3. <stem>_handler.py - business logic, dependency injection, flat conditionals\n\n"
        "Where stem is the filename without .py and without trailing _<digit>.\n\n"
        "Respond ONLY with a JSON object, no markdown fences:\n"
        '{{"modules": [{{"filename": "<stem>_io.py", "code": "<full source>"}}, '
        '{{"filename": "<stem>_auth.py", "code": "<full source>"}}, '
        '{{"filename": "<stem>_handler.py", "code": "<full source>"}}], '
        '"summary": "<one sentence>"}}'
    )

def call_claude(client, prompt, retries=3):
    for attempt in range(retries):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except (json.JSONDecodeError, anthropic.APIError) as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"Claude failed: {exc}") from exc

def stem_of(filename):
    base = Path(filename).stem
    return re.sub(r"_\d+$", "", base)

def main():
    if not TEST_INPUTS_PATH.exists():
        print(f"ERROR: {TEST_INPUTS_PATH} not found", file=sys.stderr)
        sys.exit(1)
    test_inputs = json.loads(TEST_INPUTS_PATH.read_text())
    client      = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    results     = []
    total       = len(test_inputs)
    for idx, item in enumerate(test_inputs, 1):
        inp = item.get("input", item)
        filename = inp.get("filename", item["id"])
        print(f"[{idx}/{total}] Refactoring {filename} ...")
        try:
            prompt = build_prompt(inp)
            claude_output = call_claude(client, prompt)
            results.append({
                "id": item["id"],
                "output": {
                    "original_filename": filename,
                    "refactored_modules": claude_output.get("modules", []),
                    "summary": claude_output.get("summary", ""),
                    "issues_addressed": inp.get("issues", []),
                },
            })
            print(f"  Done - {len(claude_output.get('modules', []))} modules")
        except Exception as exc:
            print(f"  Error: {exc}", file=sys.stderr)
            results.append({
                "id": item["id"],
                "output": {
                    "original_filename": filename,
                    "refactored_modules": [],
                    "summary": f"ERROR: {exc}",
                    "issues_addressed": [],
                },
            })
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nDone - {len(results)} results written to {RESULTS_PATH}")

if __name__ == "__main__":
    main()
