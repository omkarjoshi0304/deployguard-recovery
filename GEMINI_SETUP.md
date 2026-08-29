# Using Gemini with DeployGuard-Recovery

You now have Gemini integration ready! Here's how to use it.

## Setup (one-time)

```bash
# Set your API key (get it from https://aistudio.google.com/apikey)
export GEMINI_API_KEY="your-api-key-here"

# Or add to your shell profile to persist:
echo 'export GEMINI_API_KEY="your-key"' >> ~/.zshrc
source ~/.zshrc
```

## Quick Test (no cluster needed)

```bash
cd /Users/ojoshi/Desktop/deployguard-recovery

# Test on a saved fixture — Gemini reasons, no cluster required
python3 main.py replay --fault bad_image --llm gemini
```

**Expected output:** Gemini reads the evidence and proposes a fix (e.g., `rollback_image`).

## Full Commands

### Run one lap with Gemini
```bash
python3 main.py lap --fault bad_image --llm gemini
```
Gemini reasons → fix applied → cluster verified.

### Train with Gemini (instead of rules)
```bash
python3 main.py train --laps 2 --llm gemini
```
Training loop uses Gemini to reason about each incident. Successful fixes go into memory.

### Held-out eval with Gemini as System B
```bash
python3 main.py eval --llm gemini
```
Compares:
- **A:** Rule-based (no memory)
- **B:** Gemini (no memory) ← **real LLM reasoning**
- **C:** Memory agent (frozen, uses Gemini as fallback)

**This is the winning demo** — Gemini (B) should outperform rules (A) on complex faults, and Memory+Gemini (C) should be fastest/most consistent.

## What Changed

| File | What it does |
|---|---|
| `recovery/llm_gemini.py` | **NEW** — Gemini client implementing `LLMClient` interface |
| `main.py` | Added `--llm gemini` flag to `lap`, `train`, `eval`, `replay` commands |

The mock brain (`llm_mock.py`) is still the default — use `--llm gemini` to switch.

## Troubleshooting

**"ModuleNotFoundError: No module named 'google.genai'"**
```bash
pip3 install --break-system-packages google-genai
```
(The code uses the new unified SDK `google-genai` / `from google import genai` —
not the deprecated `google-generativeai` package.)

**"GEMINI_API_KEY must be set"**
```bash
export GEMINI_API_KEY="your-key"
```

**"Gemini returned unparseable JSON"**
- Gemini sometimes wraps JSON in markdown fences — the parser handles this
- If it persists, check the raw response in the terminal output

## Next: Run the Winning Eval

```bash
# 1. Train with Gemini (optional — can reuse existing memory)
python3 main.py train --laps 2 --llm gemini

# 2. Freeze
python3 main.py freeze

# 3. Eval with Gemini as System B
python3 main.py eval --llm gemini

# Results saved to eval/results_bad_command.json
```

The demo story becomes: "System B (Gemini) reasons better than rules (A), and System C (Memory+Gemini) is the fastest because it recalls proven fixes instantly."
