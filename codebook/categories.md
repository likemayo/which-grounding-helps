# Cognitive-cause categories

Six categories. Every submission gets exactly one.

The framework is adapted from Zehetmeier, Böttcher, Brüggemann-Klein & Thurner (2015), narrowed for
a corpus of single-function introductory Java exercises, where categories such as *algorithmic
choice* or *architectural error* have no room to appear. The narrowing is a methodological
adaptation and is reported as such.

Each category below is stated with the question that discriminates it from its nearest neighbour.
When two categories both seem to fit, that question — not intuition about the student — decides.

---

## `MENTAL_TYPO`

**Thought it right, wrote it wrong.** The rest of the code proves the student knows the correct
rule; the defect appears only in some of the places the rule applies.

*Discriminating question:* is the same judgment made correctly elsewhere in this submission?
If yes, it is a slip. If it is uniformly wrong, it is a belief — see `MISCONCEPTION`.

---

## `KNOWLEDGE_GAP`

**Missing the syntax or the API, and so unable to express the intent at all.** The student is
reaching for something that does not exist, or does not exist in that form.

*Discriminating question:* is the student reaching for a capability, or applying one incorrectly?
Reaching for a non-existent `String.reverse()` is a gap. Calling `substring` with the wrong bounds
is not — they know the method exists and hold a wrong belief about its semantics.

---

## `MISCONCEPTION`

**Holds a specific false belief, and the code faithfully implements it.**

*Discriminating question:* can you state the belief in one sentence beginning "he thinks…"?
If you cannot, do not use this category. "He thinks `substring(a, b)` includes index `b`" qualifies.
"He is confused about strings" does not.

---

## `STRUCTURAL_BLINDNESS`

**Every expression is individually defensible; the arrangement is wrong.** Moving code fixes it —
a return inside the loop that belongs after it, an update before the test that belongs after.

*Discriminating question:* can the submission be repaired by moving existing lines, without
rewriting any of them? If yes, this is the category.

---

## `SPEC_MISREADING`

**Cleanly implements a coherent rule — just not the one the problem asked for.**

*Discriminating question:* can you state the rule the code *does* implement, and is it internally
consistent? If the code is simply wrong rather than answering a different question, it is not this.

Note: this category is undecidable without the problem statement, by construction. C1 and C2 cannot
achieve recall on it. That is a property of the construct, not a defect in the prompts, and is one
of the things the ablation is designed to expose.

---

## `INDETERMINATE`

**The evidence does not support a judgment.**

This is a real category, not a skip key. Reach for it when the code is too fragmentary to reveal
intent, when two categories are equally supported and nothing discriminates them, or when the
student's intent is genuinely unrecoverable.

A model that returns a confident label where a human annotator judges the evidence insufficient is
overconfident. Rate of agreement on `INDETERMINATE` is reported as a calibration measure.
