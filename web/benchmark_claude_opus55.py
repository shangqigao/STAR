from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = Path("/Users/sg2162/Datasets/CancerDatasets/STAR")
DEFAULT_OUTPUT = PROJECT_ROOT / "answers" / "claude-opus-5-5.jsonl"
MANIFEST_PATH = PROJECT_ROOT / "manifests" / "images.json"
SPLIT_PATH = PROJECT_ROOT / "assignments" / "mllm_split.json"
PROMPTS_PATH = PROJECT_ROOT / "assignments" / "mllm_prompts.json"
MODEL = "claude-opus-5-5"
INPUT_PRICE_PER_MTOK = 4.0
OUTPUT_PRICE_PER_MTOK = 20.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def completed_image_ids(path: Path) -> set[str]:
    completed = set()
    if not path.exists():
        return completed
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") == "complete" and row.get("image_id"):
                completed.add(row["image_id"])
    return completed


def image_path(item: dict, data_dir: Path) -> Path:
    filename = Path(item["image_path"]).name
    return data_dir / item["dataset"] / "vis_check" / filename


def media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")


def usage_dict(response) -> dict[str, int]:
    usage = response.usage
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    return {field: int(getattr(usage, field, 0) or 0) for field in fields}


def response_text(response) -> str:
    return "\n".join(
        str(block.text)
        for block in response.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ).strip()


def parse_choice(raw: str, choices: list[str]) -> str | None:
    candidate = raw.strip().strip("`\"'").strip()
    if candidate.endswith("."):
        candidate = candidate[:-1].rstrip()
    exact = {choice.casefold(): choice for choice in choices}
    return exact.get(candidate.casefold())


def question_text(prompt: str, choices: list[str], retry: bool = False) -> str:
    prefix = "Your previous response was invalid. " if retry else ""
    options = "\n".join(f"- {choice}" for choice in choices)
    return (
        f"{prefix}{prompt}\n\nAllowed options:\n{options}\n\n"
        "Return exactly one allowed option and nothing else."
    )


def ask_choice(
    client,
    *,
    image_data: str,
    image_media_type: str,
    system_prompt: str,
    prompt: str,
    choices: list[str],
    effort: str,
    max_tokens: int,
    max_attempts: int,
) -> tuple[str, str, dict, str]:
    last_raw = ""
    usage_total = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    model_returned = ""
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": image_media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": question_text(prompt, choices, retry=attempt > 1),
                        },
                    ],
                }],
            )
        except Exception as error:
            retryable = error.__class__.__name__ in {
                "APIConnectionError",
                "APITimeoutError",
                "InternalServerError",
                "RateLimitError",
            }
            if not retryable or attempt == max_attempts:
                raise
            delay = min(60.0, (2 ** (attempt - 1)) + random.random())
            print(f"  transient {error.__class__.__name__}; retrying in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay)
            continue

        model_returned = str(response.model)
        last_raw = response_text(response)
        for field, value in usage_dict(response).items():
            usage_total[field] += value
        choice = parse_choice(last_raw, choices)
        if choice is not None:
            return choice, last_raw, usage_total, model_returned
        if attempt < max_attempts:
            print(f"  invalid answer {last_raw!r}; retrying", file=sys.stderr)
    raise ValueError(f"No valid option after {max_attempts} attempts; last response: {last_raw!r}")


def total_usage(per_question: dict[str, dict[str, int]]) -> dict[str, int]:
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    return {
        field: sum(question.get(field, 0) for question in per_question.values())
        for field in fields
    }


def estimated_cost(usage: dict[str, int]) -> float:
    # This runner does not enable prompt caching, so base input/output rates apply.
    return round(
        usage["input_tokens"] / 1_000_000 * INPUT_PRICE_PER_MTOK
        + usage["output_tokens"] / 1_000_000 * OUTPUT_PRICE_PER_MTOK,
        6,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen STAR Q1-Q4 benchmark with Claude Opus 5.5."
    )
    parser.add_argument("--data_dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, help="Process at most this many unfinished images.")
    parser.add_argument("--max_tokens", type=int, default=256)
    parser.add_argument("--max_attempts", type=int, default=3)
    parser.add_argument(
        "--effort",
        choices=("low", "medium", "high", "xhigh", "max"),
        default="low",
    )
    parser.add_argument("--dry_run", action="store_true")
    args = parser.parse_args()

    manifest = {item["image_id"]: item for item in read_json(MANIFEST_PATH)}
    split = read_json(SPLIT_PATH)
    prompt_spec = read_json(PROMPTS_PATH)
    split_ids = split["image_ids"]
    done = completed_image_ids(args.output)
    pending = [image_id for image_id in split_ids if image_id not in done]
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be positive.")
        pending = pending[:args.limit]

    missing_manifest = [image_id for image_id in pending if image_id not in manifest]
    if missing_manifest:
        raise SystemExit(f"{len(missing_manifest)} split images are absent from the manifest.")
    missing_files = [
        str(image_path(manifest[image_id], args.data_dir))
        for image_id in pending
        if not image_path(manifest[image_id], args.data_dir).is_file()
    ]
    if missing_files:
        raise SystemExit(f"{len(missing_files)} image files are missing; first: {missing_files[0]}")

    print(json.dumps({
        "model": MODEL,
        "split": str(SPLIT_PATH),
        "prompt_spec": str(PROMPTS_PATH),
        "split_total": len(split_ids),
        "already_complete": len(done.intersection(split_ids)),
        "selected_this_run": len(pending),
        "output": str(args.output),
        "effort": args.effort,
        "max_tokens": args.max_tokens,
    }, indent=2))
    if args.dry_run or not pending:
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set.")
    try:
        import anthropic
    except ImportError as error:
        raise SystemExit("Install the SDK with: python3 -m pip install -r requirements-opus55.txt") from error

    client = anthropic.Anthropic()
    questions = {question["number"]: question for question in prompt_spec["questions"]}
    system_prompt = prompt_spec["system_prompt"]
    run_cost = 0.0
    run_complete = 0

    for position, image_id in enumerate(pending, start=1):
        item = manifest[image_id]
        path = image_path(item, args.data_dir)
        image_data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        raw_responses = {}
        usage_by_question = {}
        answers = {}
        model_returned = ""
        print(f"[{position}/{len(pending)}] {image_id}", flush=True)
        try:
            for number, field in (
                ("Q1", "q1_region"),
                ("Q2", "q_lymph_node"),
                ("Q3", "q2_site"),
                ("Q4", "q4_quality_issue"),
            ):
                question = questions[number]
                if number == "Q3":
                    choices = prompt_spec["q3_choice_matrix"][answers["q1_region"]][answers["q_lymph_node"]]
                    prompt = question["prompt_template"].format(**answers)
                else:
                    choices = question["choices"]
                    prompt = question["prompt"]
                choice, raw, usage, returned = ask_choice(
                    client,
                    image_data=image_data,
                    image_media_type=media_type(path),
                    system_prompt=system_prompt,
                    prompt=prompt,
                    choices=choices,
                    effort=args.effort,
                    max_tokens=args.max_tokens,
                    max_attempts=args.max_attempts,
                )
                answers[field] = choice
                raw_responses[number.lower()] = raw
                usage_by_question[number.lower()] = usage
                model_returned = returned or model_returned
            usage = total_usage(usage_by_question)
            cost = estimated_cost(usage)
            row = {
                "timestamp": utc_now(),
                "status": "complete",
                "user_id": "claude-opus-5-5",
                "user_type": "mllm",
                "model_requested": MODEL,
                "model_returned": model_returned,
                "effort": args.effort,
                "max_tokens": args.max_tokens,
                "image_id": image_id,
                "dataset": item["dataset"],
                **answers,
                "raw_responses": raw_responses,
                "usage_by_question": usage_by_question,
                "usage": usage,
                "estimated_standard_cost_usd": cost,
            }
            append_jsonl(args.output, row)
            run_cost += cost
            run_complete += 1
            print(
                f"  {answers['q1_region']} | {answers['q_lymph_node']} | "
                f"{answers['q2_site']} | {answers['q4_quality_issue']} | ${cost:.4f}",
                flush=True,
            )
        except Exception as error:
            append_jsonl(args.output, {
                "timestamp": utc_now(),
                "status": "error",
                "user_id": "claude-opus-5-5",
                "user_type": "mllm",
                "model_requested": MODEL,
                "effort": args.effort,
                "max_tokens": args.max_tokens,
                "image_id": image_id,
                "dataset": item["dataset"],
                "partial_answers": answers,
                "raw_responses": raw_responses,
                "usage_by_question": usage_by_question,
                "error_type": error.__class__.__name__,
                "error": str(error),
            })
            print(f"  ERROR {error.__class__.__name__}: {error}", file=sys.stderr, flush=True)

    print(json.dumps({
        "completed_this_run": run_complete,
        "errors_this_run": len(pending) - run_complete,
        "estimated_standard_cost_this_run_usd": round(run_cost, 4),
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
