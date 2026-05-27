# Key Decisions

## 1. Claude as the refactoring engine
The solution calls claude-sonnet-4-6 via the Anthropic Python SDK. Claude receives the full legacy code, the list of issues, and the refactoring goals in a single prompt, then returns structured JSON containing the three refactored modules.

## 2. Three-module split: IO / Auth / Handler
Every legacy file has exactly the same three concerns tangled together: file I/O, token authorisation, and business logic. Splitting into _io.py, _auth.py, and _handler.py maps one-to-one onto those concerns and is consistent across all files.

## 3. Structured JSON output from Claude
The prompt asks Claude to respond with a pure JSON object. The solution strips any accidental fences and parses the response. This keeps the pipeline deterministic with no ambiguity about module boundaries.

## 4. Retry with exponential back-off
Each call_claude() call retries up to three times with 2**attempt second delays to handle transient API rate-limit errors without crashing the run.

## 5. Graceful degradation per item
If one file fails, the error is recorded in results.json for that item and processing continues. The final file always has one entry per input.
