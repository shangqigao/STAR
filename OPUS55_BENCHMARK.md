# Claude Opus 5.5 benchmark

This runner evaluates `claude-opus-5-5` on the frozen 10,565-image STAR MLLM
split using the exact Q1–Q4 prompt specification. Each image receives four
independent API calls. Q3 choices are generated from the model's own Q1 and Q2
answers, matching the web workflow.

## Setup

Create an Anthropic API key and add billing in the Anthropic Console. Then run:

```bash
cd /Users/sg2162/Library/CloudStorage/OneDrive-UniversityofCambridge/backup/project/STAR
python3 -m pip install -r requirements-opus55.txt
export ANTHROPIC_API_KEY="your-api-key"
```

Never put the API key in a script, JSON output, shell history, or Git repository.

## Validate without spending money

```bash
python3 web/benchmark_claude_opus55.py --dry_run --limit 10
```

## One-image connection test

```bash
python3 web/benchmark_claude_opus55.py --limit 1
```

Check `answers/claude-opus-5-5.jsonl` before proceeding.

## Recommended 100-image pilot

```bash
python3 web/benchmark_claude_opus55.py --limit 100
```

The runner resumes automatically. Images already saved with `status: complete`
are skipped, while errors are attempted again on the next run.

## Full benchmark

```bash
python3 web/benchmark_claude_opus55.py
```

The default configuration uses adaptive thinking at low effort, a 256-token
output ceiling per question, exact-option validation, up to three attempts, and
standard synchronous API pricing. Every completed record stores the four
answers, raw responses, per-question usage, total token usage, returned model
identifier, and estimated USD cost.

The model receives only the image pixels, standardized prompt, and allowed
choices. It never receives the image ID, filename, dataset, human answer,
ground truth, or accuracy feedback.
