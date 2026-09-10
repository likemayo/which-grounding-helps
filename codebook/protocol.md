# Annotation protocol

## What annotators see

The **union of all four evidence conditions**: student code, `javac` output where the submission
failed to compile, the full problem statement, and the per-test-case table with input, expected
output, and pass/fail.

Human labels are the ground truth. If the model in some condition had access to information the
annotator lacked, "correct" and "lucky" would be indistinguishable.

## Division of labour

| | Scope |
|---|---|
| Annotator A | all 264 |
| Annotator B | the 100-item double-annotated subset |

The 100 are drawn 35 / 25 / 40 across the three strata rather than proportionally, so that
per-stratum agreement is estimable rather than only the pooled figure.

## Rules

1. **No discussion of specific items during annotation.** A κ computed after the annotators have
   talked through the items is not a κ. Reconciliation happens once, after both passes are complete.
2. **Annotate your own sheet only.** Do not look at the other annotator's labels.
3. **Every item gets a label.** `INDETERMINATE` when the evidence does not support a judgment — it
   is a category, not a blank.
4. **The `note` column is optional** and is for items you hesitated on. One sentence on what the
   hesitation was. These drive the reconciliation meeting.

## The three decision rules

These were derived from the data during a pilot pass and are fixed for the main annotation.

### 1. Consistency test

Where the same judgment appears in several places and is correct in some and wrong in others, the
error is a **slip**. Where it is uniformly wrong, it reflects a **belief**.

This is the primary discriminator between `MENTAL_TYPO` and `MISCONCEPTION`, and it is applied
before any impression of how "basic" the mistake seems.

### 2. Copy-paste exception

Novices frequently duplicate a branch and edit the constant, so a single slip can present as several
consistent errors — which would fool rule 1 into reading a belief. **Occurrences within a copied
block count once.**

### 3. Compiler messages are symptoms, not categories

A `javac` message names where the compiler stopped, not why the student went wrong. Read the message
to locate the defect, then return to the code to classify it.

`cannot find symbol` may be a `KNOWLEDGE_GAP` (the student does not know the API exists) or a
`MENTAL_TYPO` (the identifier is mistyped). **The discriminator is whether that symbol is used
correctly elsewhere in the same submission.**

Never map a message class onto a category. Doing so would make C2 look informative by construction,
which is precisely the effect the study is trying to measure.

## Reconciliation

After both passes are complete:

1. Compute Cohen's κ, overall and per stratum, before any discussion.
2. Work through disagreements to consensus labels.
3. Report the pre-reconciliation κ. Consensus labels are the ground truth for the model comparison;
   the κ that is reported is the one from independent annotation.
