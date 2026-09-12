# Which Grounding Helps?

**Evidence type and the reliability of LLM error diagnosis in introductory programming.**

Work in progress, aimed at LAK 2027. This repository holds the corpus-construction code, the
annotation codebook, and the sampling procedure. It does not hold the paper, and it does not
redistribute the underlying data — see [`data/README.md`](data/README.md) for how to obtain it.

---

## The question

Automated feedback systems increasingly ask a language model not just *what* is wrong with a
student's program but *why* — to name the cognitive cause behind the error, so that feedback can
address the misconception rather than the symptom. Such systems are given whatever context is
convenient: sometimes only the code, sometimes the compiler output, sometimes the full problem
specification and test results.

Whether these forms of evidence are interchangeable is not established. They are treated as if
more context were uniformly better.

**RQ.** How does the reliability of an LLM's inference about the *cognitive cause* of a programming
error change as the evidence available to it is increased?

**H1 (asymmetry).** The benefit of additional grounding depends on the error type. Compiler output
should substantially improve inference for submissions that fail to compile, and contribute close to
nothing for submissions that compile and produce an incorrect result — because for the latter there
is no compiler message to add. For those, only execution evidence carries information.

If H1 holds, a single aggregate agreement figure across all errors — which is what prior work
reports — averages over two regimes in which the same evidence has very different value.

---

## The corpus

CodeWorkout Spring 2019 student submissions, assembled from two public releases that are each
incomplete for this purpose:

| Source | Problem statements | Per-test-case outcomes | Compiler messages |
|---|---|---|---|
| `umass-ml4ed/tiktoc` (LAK 2025) | yes | yes | no |
| CMU DataShop 3458, original export | no | no | yes |

Neither release alone supports a four-level grounding ladder. `src/merge_corpus.py` joins them on
`(ProblemID, ServerTimestamp, normalized source text)`.

**The first two fields are not enough.** 801 pairs collide — two students submitting to the same
problem within the same second — which inflates the join by roughly 4%. Adding normalized source
text resolves it exactly.

Result: **13,083** submissions carrying all three signals. 3,951 fail to compile; 9,131 compile and
are still incorrect. Compiler messages are genuine `javac` output, averaging **1.41** diagnostics
per failed compilation (median 1; 85% carry exactly one).

That figure is lower than the 2.24 of the full CodeWorkout export, and the difference is a property
of the subset, not a loss in the merge: tiktoc covers 17 of CodeWorkout's 50 problems, and failures
on those problems are simpler. This was checked submission by submission against the raw export —
all 3,951 failing submissions matched, with zero diagnostics dropped.

### Three traps in the source data

Each is checked programmatically; each cost a day to find.

**1. The test-case CSV is MySQL-escaped, not RFC 4180.** It uses `\"` where RFC 4180 uses `""`.
`pandas.read_csv` raises `Expected 13 fields in line 212, saw 14`. The tempting fix,
`on_bad_lines='skip'`, silently drops 48 of 585 rows and misaligns every `binary_correctness`
index downstream. Correct parsing:

```python
csv.reader(fh, doublequote=False, escapechar="\\")
```

**2. A failed compilation is several rows, not one.** In the ProgSnap2 export the submission is a
`Run.Program` row and each diagnostic is a separate `Compile.Error` row. Filtering to `Run.Program`
before collecting messages keeps at most one diagnostic per submission — and leaves every row count
intact, so nothing downstream complains. `merge_corpus.py` groups the `Compile.Error` rows on the
join key and asserts the resulting mean; that assertion is the only thing that catches this.

**3. Row counts aligning does not mean contents align.** The correctness vector is positional
against the ordered test-case table, so a count-based sanity check passes while the data is
scrambled. `src/sample_batch2.py` pins two reference values (`P13#13`, `P40#1`) and exits if either
fails to match, and index alignment was verified on all 12,139 candidate submissions with zero
misalignments.

---

## Conditions

Four conditions, differing only in the evidence block supplied to the model. System prompt, category
definitions, decision procedure, and output schema are byte-identical across conditions, enforced
programmatically before each run — otherwise differences in output cannot be attributed to the
evidence.

| | Evidence |
|---|---|
| **C1** | Student code |
| **C2** | + compiler output (static evidence) |
| **C3** | + problem statement |
| **C4** | + per-test-case input, expected output, and outcome (execution evidence) |

A submission that failed to compile was never executed, so it has no outcomes. Those items carry
the test-case inputs and expected outputs marked `not executed (compilation failed)` — never a
fabricated pass/fail vector. The zero vector that `binary_correctness` stores for an unrun
submission is a default, not a result, and presenting it would tell the model the program ran and
failed every case.

**C2 adds nothing for a submission that compiles.** There is no diagnostic to supply, so for those
206 of the 264 items the C1 and C2 prompts are byte-identical. That is deliberate rather than a
defect: any label difference between two byte-identical prompts is the model's run-to-run
variation, which gives the design a measured resolution floor instead of an assumed one.

---

## Sample

264 submissions:

| Stratum | n |
|---|---|
| Fails to compile | 58 |
| Compiles, all tests fail | 31 |
| Compiles, some tests fail | 175 |

**The middle stratum is the design's control.** In an initial 204-item sample, failure severity was
almost perfectly confounded with compilation status: 28 of 29 total-failure items were also
compilation failures. Any measured C2 benefit would then have been unattributable — it could equally
have reflected that total failures are simply easier to diagnose. Comparing 58 compilation failures
against 31 submissions that compile but fail every test holds severity roughly constant and isolates
the contribution of compiler output. The stratum is scarce (162 such cases in the whole corpus),
which bounds how far it can be enlarged.

Other sampling constraints: one submission per `(student, problem)` pair, since consecutive attempts
often differ by a single token and would both inflate agreement and violate independence;
stratification by concept family; near-miss cases oversampled relative to base rate, as single-test
failures are where the slip-versus-belief distinction is most contested. Design weights are reported
so the population distribution can be recovered.

100 of the 264 are labeled independently by both annotators — 35 / 25 / 40 across strata rather than
proportionally, so per-stratum agreement is estimable.

---

## Ground truth

Six cognitive-cause categories and three decision rules, in [`codebook/`](codebook/). Adapted from
Zehetmeier et al. (2015), narrowed for a corpus of single-function introductory exercises.

`INDETERMINATE` is a substantive category, not a skip key: a model that returns a confident label
where a human annotator judges the evidence insufficient is overconfident, and that is itself a
result.

Annotators see the union of all four evidence conditions. Human labels are the ground truth, so if
the model in some condition had access to information the annotator lacked, "correct" and "lucky"
would be indistinguishable.

---

## Layout

```
src/merge_corpus.py     Join the two releases; assert the published counts
src/sample_batch2.py    Draw the supplementary stratum that breaks the confound
src/build_items.py      Merge 204 + 60 into the 264-item set, patching javac messages
src/make_sheets.py      Emit per-annotator XLSX with validated dropdowns
codebook/categories.md  The six categories, with the discriminating test for each
codebook/protocol.md    Annotation procedure and the three decision rules
data/README.md          How to obtain the sources; why they are not vendored here
```

## Running it

```bash
pip install -r requirements.txt
python src/merge_corpus.py      # writes merged.pkl, asserts n = 13,083
python src/sample_batch2.py     # writes batch2.json
python src/build_items.py       # writes items_264.json
python src/make_sheets.py       # writes the two annotator workbooks
```

Every script fails loudly rather than degrading: a count that does not reproduce, a reference value
that does not match, or a compilation failure missing its `javac` message will stop the pipeline.

---

## Status

Corpus merged and verified. Sampling complete. Codebook fixed. Annotation underway with a second
annotator ([@Sophie-l-l](https://github.com/Sophie-l-l)).

Model runs are in progress. Nothing here is a result: no agreement figure, no condition contrast
and no κ is reported in this repository, and none should be inferred from it. Results belong to the
paper.

## License

Code: MIT (see [`LICENSE`](LICENSE)). The codebook text is CC BY 4.0. The underlying data is
governed by the terms of its original releases and is not redistributed here.
