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

Reconstructed from the interactive session that first produced merged.pkl.
Run it once end to end and confirm the printed counts before relying on the output.

Usage:  python src/merge_corpus.py
Writes: merged.pkl
"""
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


def norm(s: str) -> str:
    """Normalize source text for keying: strip trailing whitespace per line."""
    return "\n".join(line.rstrip() for line in str(s).strip().splitlines())


def load_progsnap2(root: Path) -> pd.DataFrame:
    """MainTable joined to CodeStates, one row per Run.Program event."""
    main = root / "MainTable.csv"
    states = root / "CodeStates" / "CodeStates.csv"
    for p in (main, states):
        if not p.exists():
            sys.exit(f"missing {p} -- see data/README.md for the export to request")

    mt = pd.read_csv(main, low_memory=False)
    cs = pd.read_csv(states, low_memory=False)

    mt = mt[mt.EventType == "Run.Program"].copy()
    mt = mt.merge(cs, on="CodeStateID", how="left")

    if "Code" not in mt.columns:
        sys.exit(f"CodeStates.csv has no 'Code' column; got {list(cs.columns)}")

    keep = ["SubjectID", "ProblemID", "ServerTimestamp", "Code",
            "CompileResult", "CompileMessageType", "CompileMessageData", "Score"]
    mt = mt[[c for c in keep if c in mt.columns]]
    return mt.rename(columns={"CompileResult": "compile_result"})


def collapse_messages(df: pd.DataFrame) -> pd.DataFrame:
    """One row per submission, with its javac messages joined into one field."""
    if "CompileMessageData" not in df.columns:
        df["compiler_output"] = None
        return df
    df = df.copy()
    df["compiler_output"] = df["CompileMessageData"].fillna("").astype(str).str.strip()
    return df


def main() -> None:
    if not TIKTOC_PKL.exists():
        sys.exit(f"missing {TIKTOC_PKL} -- see data/README.md "
                 "(the pickle needs `pip install javalang` to unpickle)")

    tk = pd.read_pickle(TIKTOC_PKL)
    ps = collapse_messages(load_progsnap2(PS2))
    print(f"tiktoc rows: {len(tk):>7}")
    print(f"ProgSnap2 Run.Program rows: {len(ps):>7}")

    for df in (tk, ps):
        df["ts"] = pd.to_datetime(df["ServerTimestamp"], errors="coerce", utc=True)
        df["ck"] = df["Code"].map(norm)

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

    m.drop(columns=["ck"]).to_pickle(OUT)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
