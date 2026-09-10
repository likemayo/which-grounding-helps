# Data

Nothing in this directory is vendored. Both sources have their own distribution terms, and neither
is mine to redistribute. This file is the instruction for reconstructing the corpus.

## 1. TIKTOC release — problem statements and per-test-case outcomes

```
https://github.com/umass-ml4ed/tiktoc
```

From the UMass ML4Ed group (LAK 2025). Clone it into this directory:

```bash
git clone https://github.com/umass-ml4ed/tiktoc.git data/tiktoc
```

Files used:

- `data/tiktoc/.../dataset_granular_all.pkl` — submissions with `binary_correctness`
- `data/tiktoc/test-case-query-results/test_cases-1-26-24.csv` — the test-case table

The pickle requires `javalang` at load time:

```bash
pip install javalang
```

> **Parsing warning.** `test_cases-1-26-24.csv` is MySQL-escaped, not RFC 4180 — it uses `\"` where
> RFC 4180 uses `""`. `pandas.read_csv` raises `Expected 13 fields in line 212, saw 14`.
> `on_bad_lines='skip'` "fixes" it by dropping 48 of 585 rows and silently misaligning every
> `binary_correctness` index downstream. Parse with
> `csv.reader(fh, doublequote=False, escapechar="\\")`.

## 2. CMU DataShop 3458 — compiler messages

```
https://pslcdatashop.web.cmu.edu/
```

Dataset **3458** (CodeWorkout, Spring 2019). Requires a DataShop account and acceptance of its terms
of use; access is granted per user, which is why the export is not mirrored here.

Export the **original transaction files**, not the derived tables — the `javac` messages live in the
raw event stream and are dropped from the summarized exports. Place the extracted directory at
`data/datashop-3458/`.

## 3. Build

```bash
python src/merge_corpus.py
```

Writes `merged.pkl` at the repository root and asserts the published counts. If your merge does not
reproduce **13,083 rows / 3,951 compile failures / 9,131 compile-but-incorrect**, the script exits
non-zero and prints what it got instead. Do not proceed past a failed assertion — a merge that is
off by 4% is almost certainly the two-field-key collision described in the main README.

## What is not here, and will not be

- Student source code, in any form.
- The 264-item annotation set.
- The annotators' labels.

These are derived works over data governed by the terms above. The scripts that produce them are
here; the outputs are not.
