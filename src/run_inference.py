#!/usr/bin/env python3
"""
LAK27 -- four-condition grounding ablation: model inference.

Reads the 264 annotation items from the workbench HTML (the same file the human
annotators worked from, so the model receives byte-identical evidence text),
builds one prompt per (item, condition), and calls each model N times.

Design invariants enforced in code, because the paper asserts them:

  1. The instruction block is byte-identical across C1..C4. Only the evidence
     block varies. Asserted before any call is made.
  2. Evidence is monotone: C1 subset C2 subset C3 subset C4. Asserted.
  3. For submissions that do not compile, C4 shows the test cases' inputs and
     expected outputs marked "not executed (compilation failed)" -- never a
     fabricated pass/fail vector. (Decision A.)

Resumable: results are appended to a JSONL and completed (model, item, cond,
run) keys are skipped on restart.

Usage:
    export ANTHROPIC_API_KEY=...
    export OPENAI_API_KEY=...

    python run_inference.py --workbench annotation-workbench.html \
                            --out runs.jsonl --limit 10          # pilot
    python run_inference.py --workbench annotation-workbench.html \
                            --out runs.jsonl                     # full
    python run_inference.py --out runs.jsonl --report            # cost/status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# ---------------------------------------------------------------- models

MODELS = {
    "claude-sonnet-5": {
        "provider": "anthropic",
        "in_per_m": 2.0,
        "out_per_m": 10.0,
    },
    "gpt-5-6-terra": {
        "provider": "openai",
        "in_per_m": 2.50,
        "out_per_m": 15.0,
    },
    # optional third, weak-model contrast -- off by default
    # "claude-haiku-4-5-20251001": {"provider": "anthropic",
    #                               "in_per_m": 1.0, "out_per_m": 5.0},
}

CONDITIONS = ["C1", "C2", "C3", "C4"]
LABELS = ["MENTAL_TYPO", "KNOWLEDGE_GAP", "MISCONCEPTION",
          "STRUCTURAL_BLINDNESS", "SPEC_MISREADING", "INDETERMINATE"]

SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": LABELS},
        "rationale": {"type": "string"},
        "confidence": {"type": "integer", "enum": [1, 2, 3]},
    },
    "required": ["label", "rationale", "confidence"],
    "additionalProperties": False,
}

# ------------------------------------------------------- instruction block
# Identical for every condition. Do not interpolate anything item-specific or
# condition-specific into this string.

INSTRUCTIONS = """\
You are labelling the cognitive cause of an error in an introductory Java \
submission written by a student. Assign exactly one of six categories.

MENTAL_TYPO
    Thought it right, wrote it wrong. The rest of the code proves the student
    knows the correct rule; the defect appears only in some of the places the
    rule applies.

KNOWLEDGE_GAP
    Missing the syntax or API, and so unable to express the intent at all.
    Reaching for a capability that does not exist, or does not exist in that
    form.

MISCONCEPTION
    Holds a specific false belief and the code implements it faithfully. You
    must be able to state the belief in one sentence beginning "he thinks...".

STRUCTURAL_BLINDNESS
    Every expression is individually defensible; the arrangement is wrong. The
    submission can be repaired by moving existing lines without rewriting any
    of them.

SPEC_MISREADING
    Cleanly implements a coherent rule other than the one asked for. You can
    state the rule the code does implement.

INDETERMINATE
    The evidence does not support a judgment.

Decision rules:

R1  Consistency. Where the same judgment is made in several places and is
    correct in some and wrong in others, the error is a slip; where it is
    uniformly wrong, it reflects a belief. This is the primary discriminator
    between MENTAL_TYPO and MISCONCEPTION, and is applied before any
    impression of how elementary the mistake appears.

R2  Copy-paste exception. Novices duplicate a branch and edit the constant, so
    a single slip can present as several consistent errors and defeat R1.
    Occurrences within a copied block count once.

R3  Compiler messages are symptoms, not categories. A diagnostic names where
    the compiler stopped, not why the student went wrong. "cannot find symbol"
    may reflect a KNOWLEDGE_GAP or a MENTAL_TYPO; the discriminator is whether
    that symbol is used correctly elsewhere in the same submission. Do not map
    a message class onto a category.

INDETERMINATE is a substantive category, not a skip key. Use it when the code
is too fragmentary to reveal intent, when two categories are equally supported
and nothing discriminates them, or when the student's intent is unrecoverable.

Return a single JSON object with exactly these fields:
  label       one of the six category names above
  rationale   one sentence
  confidence  1, 2 or 3
"""

EVIDENCE_MARK = "=== EVIDENCE ==="

# ------------------------------------------------------------ prompt build


def _tests_block(item: dict) -> str:
    rows = []
    if item["compiles"]:
        head = "Test cases (executed):"
        for t in item["tests"]:
            rows.append(f"  {t['i']:>2}  input={t['in']}   expected={t['exp']}   "
                        f"{'PASS' if t['ok'] else 'FAIL'}")
    else:
        # Decision A: show the specification the test cases encode, but never a
        # pass/fail vector -- the program never ran.
        head = ("Test cases (not executed — the submission failed to "
                "compile, so no outcomes exist):")
        for t in item["tests"]:
            rows.append(f"  {t['i']:>2}  input={t['in']}   expected={t['exp']}")
    return head + "\n" + "\n".join(rows)


def evidence(item: dict, cond: str) -> str:
    """Monotone evidence blocks. Each level only adds."""
    parts = [f"Student code:\n{item['code']}"]

    if cond in ("C2", "C3", "C4"):
        # Only when a diagnostic exists. For a submission that compiles there is
        # nothing to add, so C2 is byte-identical to C1 -- which is the paper's
        # manipulation check: any difference between them in that stratum is
        # run-to-run non-determinism, and bounds the resolution of every other
        # contrast we report. Do NOT put "(compiled successfully)" here: that
        # would make C2 a different condition and forfeit the noise floor.
        co = (item.get("compiler_output") or "").strip()
        if co:
            parts.append("Compiler output:\n" + co)

    if cond in ("C3", "C4"):
        parts.append("Problem statement:\n" + item["prompt"].strip())

    if cond == "C4":
        parts.append(_tests_block(item))

    return EVIDENCE_MARK + "\n\n" + "\n\n".join(parts)


def build_prompt(item: dict, cond: str) -> str:
    return INSTRUCTIONS + "\n" + evidence(item, cond)


def check_invariants(items: list[dict]) -> None:
    """The two properties the paper asserts. Fail loudly, before spending money."""
    for item in items:
        blocks = {c: build_prompt(item, c) for c in CONDITIONS}

        shared = {b.split(EVIDENCE_MARK)[0] for b in blocks.values()}
        if len(shared) != 1:
            sys.exit(f"FAILED [{item['id']}]: instruction block differs across "
                     f"conditions")

        ev = {c: evidence(item, c) for c in CONDITIONS}
        for a, b in zip(CONDITIONS, CONDITIONS[1:]):
            stripped = ev[a][len(EVIDENCE_MARK):].strip()
            if stripped not in ev[b]:
                sys.exit(f"FAILED [{item['id']}]: {a} evidence is not a prefix "
                         f"of {b} -- monotonicity broken")

        if not item["compiles"] and "PASS" in ev["C4"]:
            sys.exit(f"FAILED [{item['id']}]: a non-compiling submission was "
                     f"given execution outcomes")

    print(f"invariants OK on {len(items)} items "
          f"(instruction block identical; evidence monotone; "
          f"no fabricated outcomes)")


# ----------------------------------------------------------------- loading


def load_items(path: Path) -> list[dict]:
    html = path.read_text(encoding="utf-8")
    i = html.index("const ALL = ") + len("const ALL = ")
    items, _ = json.JSONDecoder().raw_decode(html[i:])
    if len(items) != 264:
        print(f"WARNING: expected 264 items, found {len(items)} -- is this the "
              f"current workbench?", file=sys.stderr)
    return items


# --------------------------------------------------------------- providers


def call_anthropic(model: str, prompt: str, timeout: int = 120) -> tuple[dict, dict]:
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 512,
            "temperature": 0,
            "tools": [{
                "name": "label",
                "description": "Record the cognitive-cause label.",
                "input_schema": SCHEMA,
            }],
            "tool_choice": {"type": "tool", "name": "label"},
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    out = None
    for block in body.get("content", []):
        if block.get("type") == "tool_use":
            out = block["input"]
            break
    usage = body.get("usage", {})
    return out, {"in": usage.get("input_tokens", 0),
                 "out": usage.get("output_tokens", 0)}


def call_openai(model: str, prompt: str, timeout: int = 120) -> tuple[dict, dict]:
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "label", "strict": True, "schema": SCHEMA},
        },
    }
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                 "Content-Type": "application/json"},
        json=payload, timeout=timeout,
    )
    if r.status_code == 400 and "temperature" in r.text:
        payload.pop("temperature")          # some models fix temperature
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                     "Content-Type": "application/json"},
            json=payload, timeout=timeout,
        )
    r.raise_for_status()
    body = r.json()
    text = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    return json.loads(text), {"in": usage.get("prompt_tokens", 0),
                              "out": usage.get("completion_tokens", 0)}


CALLERS = {"anthropic": call_anthropic, "openai": call_openai}


def valid(out) -> bool:
    return (isinstance(out, dict)
            and out.get("label") in LABELS
            and isinstance(out.get("rationale"), str)
            and out.get("confidence") in (1, 2, 3))


# ------------------------------------------------------------------ runner


def one_call(model: str, item: dict, cond: str, run: int) -> dict:
    prompt = build_prompt(item, cond)
    caller = CALLERS[MODELS[model]["provider"]]
    rec = {
        "model": model, "item_id": item["id"], "cond": cond, "run": run,
        "prompt_sha1": hashlib.sha1(prompt.encode()).hexdigest()[:12],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for attempt in (1, 2):                 # retry once, then record the failure
        try:
            out, usage = caller(model, prompt)
            rec["tokens_in"], rec["tokens_out"] = usage["in"], usage["out"]
            if valid(out):
                rec.update(status="ok", **out)
                return rec
            rec["raw"] = json.dumps(out)[:500]
        except requests.HTTPError as e:
            rec["error"] = f"http {e.response.status_code}: {e.response.text[:200]}"
            if e.response.status_code in (429, 500, 502, 503, 529):
                time.sleep(5 * attempt)
                continue
        except Exception as e:             # noqa: BLE001 -- record, do not drop
            rec["error"] = f"{type(e).__name__}: {e}"
        time.sleep(2 * attempt)
    rec["status"] = "parse_failure" if "raw" in rec else "error"
    return rec


def done_keys(out_path: Path) -> set[tuple]:
    keys = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("status") == "ok":
                keys.add((r["model"], r["item_id"], r["cond"], r["run"]))
    return keys


def report(out_path: Path) -> None:
    from collections import Counter
    rows = [json.loads(l) for l in out_path.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    print(f"records: {len(rows)}")
    print("status:", dict(Counter(r.get("status") for r in rows)))
    for model, cfg in MODELS.items():
        sub = [r for r in rows if r["model"] == model]
        if not sub:
            continue
        ti = sum(r.get("tokens_in", 0) for r in sub)
        to = sum(r.get("tokens_out", 0) for r in sub)
        cost = ti / 1e6 * cfg["in_per_m"] + to / 1e6 * cfg["out_per_m"]
        ok = sum(1 for r in sub if r.get("status") == "ok")
        print(f"  {model:<28} {ok:>5}/{len(sub):<5} ok   "
              f"{ti/1e6:.2f}M in  {to/1e6:.2f}M out   ${cost:.2f}")
        lab = Counter(r["label"] for r in sub if r.get("status") == "ok")
        print(f"      labels: {dict(lab)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workbench", type=Path,
                    default=Path("annotation-workbench.html"))
    ap.add_argument("--out", type=Path, default=Path("runs.jsonl"))
    ap.add_argument("--models", nargs="*", default=list(MODELS))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0,
                    help="only the first N items (pilot)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    if a.report:
        report(a.out)
        return

    items = load_items(a.workbench)
    check_invariants(items)                 # always, on the full set
    if a.check_only:
        return
    if a.limit:
        items = items[:a.limit]

    for m in a.models:
        env = "ANTHROPIC_API_KEY" if MODELS[m]["provider"] == "anthropic" \
              else "OPENAI_API_KEY"
        if not os.environ.get(env):
            sys.exit(f"{env} is not set (needed for {m})")

    done = done_keys(a.out)
    jobs = [(m, it, c, r)
            for m in a.models for it in items
            for c in CONDITIONS for r in range(1, a.runs + 1)
            if (m, it["id"], c, r) not in done]

    print(f"{len(items)} items x {len(CONDITIONS)} conditions x {a.runs} runs "
          f"x {len(a.models)} models")
    print(f"{len(done)} already complete, {len(jobs)} to run")
    if not jobs:
        return

    n = 0
    with a.out.open("a", encoding="utf-8") as fh, \
         ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = [pool.submit(one_call, *j) for j in jobs]
        for fut in as_completed(futures):
            rec = fut.result()
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            if n % 25 == 0 or n == len(jobs):
                print(f"  {n}/{len(jobs)}", flush=True)

    print()
    report(a.out)


if __name__ == "__main__":
    main()
