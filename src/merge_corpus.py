#!/usr/bin/env python3
"""
Join the two public releases of CodeWorkout Spring 2019 into one corpus carrying
problem statements, per-test-case outcomes, AND compiler messages.

  tiktoc  (umass-ml4ed, LAK 2025)  ->  prompt, binary_correctness
  DataShop 3458, ProgSnap2 export  ->  javac messages

Join key: (ProblemID, ServerTimestamp, normalized source text).

Why all three fields. (ProblemID, ServerTimestamp) alone collides on 801 pairs --
two students submitting to the same problem within the same second -- which inflates
the join by roughly 4%. Adding normalized source resolves it exactly. The script
asserts both the collision count and the final row count; if either fails to
reproduce, it exits non-zero rather than writing a corpus you would then trust.

Usage:  python src/merge_corpus.py
Writes: merged.pkl
"""
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TIKTOC_PKL = ROOT / "data" / "tiktoc" / "dataset_granular_all.pkl"
PS2 = ROOT / "data" / "datashop-3458"          # ProgSnap2 export root
OUT = ROOT / "merged.pkl"

# Published counts. These are assertions, not documentation.
EXPECT_ROWS = 13083
EXPECT_FAIL = 3951
EXPECT_WRONG = 9131
EXPECT_COLLISIONS = 801

# Mean javac diagnostics per failed compile in the merged corpus. Lower than the
# 2.24 of the full CodeWorkout export because tiktoc covers 17 of its 50 problems,
# and failures on that subset are simpler. Verified against the raw export on all
# 3,951 failing submissions: zero messages lost in the merge.
EXPECT_MSGS_PER_FAIL = 1.414


def norm(s: str) -> str:
    """Normalize source text for keying: strip trailing whitespace per line."""
    return "\n".join(line.rstrip() for line in str(s).strip().splitlines())


def load_progsnap2(root: Path) -> pd.DataFrame:
    """One row per submission, carrying ALL of its javac diagnostics."""
    main = root / "MainTable.csv"
    states = root / "CodeStates" / "CodeStates.csv"
    for p in (main, states):
        if not p.exists():
            sys.exit(f"missing {p} -- see data/README.md for the export to request")

    mt = pd.read_csv(main, low_memory=False)
    cs = pd.read_csv(states, low_memory=False)

    mt = mt.merge(cs, on="CodeStateID", how="left")
    if "Code" not in mt.columns:
        sys.exit(f"CodeStates.csv has no 'Code' column; got {list(cs.columns)}")

    mt["ts"] = pd.to_datetime(mt["ServerTimestamp"], errors="coerce", utc=True)
    mt["ck"] = mt["Code"].map(norm)
    key = ["ProblemID", "ts", "ck"]

    # One row per submission. These are NOT the only rows we need: a failed
    # compilation is SEVERAL Compile.Error rows, and filtering to Run.Program
    # before collecting them keeps at most one message per submission -- a defect
    # that leaves every row count intact and is therefore invisible to a
    # count-based sanity check.
    subs = mt[mt.EventType == "Run.Program"].copy()
    keep = ["SubjectID", "ProblemID", "ServerTimestamp", "ts", "ck", "Code",
            "CodeStateID", "Score"]
    subs = subs[[c for c in keep if c in subs.columns]].drop_duplicates(key)

    # All diagnostics for that submission, joined in event order.
    err = mt[mt.EventType == "Compile.Error"].copy()
    err["_msg"] = err["CompileMessageData"].fillna("").astype(str).str.strip()
    err = err[err._msg != ""]
    order_col = "Order" if "Order" in err.columns else "ts"
    msgs = (err.sort_values(order_col)
               .groupby(key, sort=False)["_msg"]
               .apply(lambda s: ". ".join(s))
               .rename("compiler_output")
               .reset_index())

    out = subs.merge(msgs, on=key, how="left")
    out["compile_result"] = out.compiler_output.notna().map(
        {True: "Error", False: "Success"})
    return out


def main() -> None:
    if not TIKTOC_PKL.exists():
        sys.exit(f"missing {TIKTOC_PKL} -- see data/README.md "
                 "(the pickle needs `pip install javalang` to unpickle)")

    tk = pd.read_pickle(TIKTOC_PKL)
    ps = load_progsnap2(PS2)          # already carries ts, ck, compiler_output
    print(f"tiktoc rows: {len(tk):>7}")
    print(f"ProgSnap2 submissions: {len(ps):>7}")

    tk["ts"] = pd.to_datetime(tk["ServerTimestamp"], errors="coerce", utc=True)
    tk["ck"] = tk["Code"].map(norm)

    # --- the collision the two-field key would hide -------------------------
    two = ps.duplicated(subset=["ProblemID", "ts"], keep=False)
    collisions = int(two.sum() // 2)
    print(f"(ProblemID, timestamp) collisions: {collisions} "
          f"(expected {EXPECT_COLLISIONS})")
    if collisions != EXPECT_COLLISIONS:
        print("  ^ differs from the published figure; check the export before continuing.")

    # --- three-field join ---------------------------------------------------
    key = ["ProblemID", "ts", "ck"]
    m = tk.merge(
        ps[key + ["compile_result", "compiler_output", "SubjectID"]].drop_duplicates(key),
        on=key, how="inner", suffixes=("", "_ps"),
    )

    n = len(m)
    n_fail = int((m.compile_result == "Error").sum())
    n_wrong = int((m.compile_result == "Success").sum())
    print(f"\nmerged rows:        {n:>7}  (expected {EXPECT_ROWS})")
    print(f"  fail to compile:  {n_fail:>7}  (expected {EXPECT_FAIL})")
    print(f"  compile, wrong:   {n_wrong:>7}  (expected {EXPECT_WRONG})")

    problems = [
        (n != EXPECT_ROWS, f"row count {n} != {EXPECT_ROWS}"),
        (n_fail != EXPECT_FAIL, f"compile failures {n_fail} != {EXPECT_FAIL}"),
        (n_wrong != EXPECT_WRONG, f"compile-but-wrong {n_wrong} != {EXPECT_WRONG}"),
    ]
    bad = [msg for cond, msg in problems if cond]
    if bad:
        print("\nFAILED:")
        for msg in bad:
            print("  -", msg)
        print("\nA merge that is off by roughly 4% is almost certainly the two-field-key\n"
              "collision. Do not proceed past this.")
        sys.exit(1)

    missing = m[(m.compile_result == "Error") & (m.compiler_output.fillna("") == "")]
    if len(missing):
        sys.exit(f"FAILED: {len(missing)} compile failures carry no javac message")

    # The message-count check. Row counts stay correct when diagnostics are
    # dropped, so this is the only assertion that catches it.
    k = m[m.compile_result == "Error"].compiler_output.map(
        lambda s: len(re.findall(r"error:", s or "")))
    print(f"javac diagnostics per failed compile: mean {k.mean():.3f} "
          f"(expected {EXPECT_MSGS_PER_FAIL}), median {int(k.median())}, "
          f"max {int(k.max())}")
    if abs(k.mean() - EXPECT_MSGS_PER_FAIL) > 0.05:
        sys.exit("FAILED: diagnostics per failed compile does not reproduce -- "
                 "most likely the Compile.Error rows were not all collected")

    m.drop(columns=["ck"]).to_pickle(OUT)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
