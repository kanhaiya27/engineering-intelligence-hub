# Reviewer guide: checking benchmark tasks

For: Sanvi Bhardwaj, Aryan Gupta, Avaneesh Kumar Verma (full names confirmed 2026-11-25; Aayan
and Radhesh were removed, WORK_PLAN C36). About 3 hours a day. On the command line your first name
is enough: `Sanvi`, `Aryan`, `Avaneesh`.

**Who the reviewers are (disclosed in the paper).** One of the three benchmark reviewers, Aryan
Gupta, is the project's supervisor (Mr. Aryan Gupta, UPES, the project guide). Avaneesh Kumar Verma
is the system's developer. Sanvi Bhardwaj is a reviewer.

Each benchmark task is a question about a real open-source project (Flask, FastAPI, Requests,
Pytest, Sphinx, Pylint) at one fixed version, with an answer and the exact lines of code or docs
that prove the answer. Your job is to check that the task is right. A wrong task makes every
experiment that uses it wrong.

## The four checks

| Check | Ask yourself |
|---|---|
| `question_clear` | Could a developer understand exactly what is asked? Is there only one reasonable reading? |
| `answer_correct` | Is the answer true **for the code shown**? Is anything important missing or invented? |
| `evidence_correct` | Do the shown file and lines actually contain what proves the answer? Would other lines be needed? |
| `labels_fit` | Do the stage (requirements, architecture, development, testing, code review, maintenance) and the task type fit the question? |

Only the shown lines count. They are the project at its fixed version. If you know the
answer is different in a newer version, judge it against the shown code.

## Commands (run in the repository folder)

```
python scripts/review.py next --reviewer <your first name>
```
This shows your next task and starts a timer. Then record **one** decision:

```
python scripts/review.py approve <task_id> --reviewer <name>
python scripts/review.py fix     <task_id> --reviewer <name> --failed answer_correct --note "Line 212 shows X, not Y"
python scripts/review.py reject  <task_id> --reviewer <name> --failed question_clear,evidence_correct --note "why"
```

- **approve**: all four checks pass.
- **fix**: the task is worth keeping but something specific is wrong. Say exactly what and how
  to correct it. It goes back for correction and is reviewed again.
- **reject**: the task cannot be saved (the question is unanswerable from this code, it's a
  duplicate, or it's wrong at its core).

`--failed` takes one or more of the four check names, separated by commas.

## Rules

- **Never decide on a task you drafted or asked for.** The tool refuses it.
- Test-split tasks are each checked by **two different people**, independently (D12). Under R5
  all three of you check each of the 24 pilot test tasks: those batches require 3 reviews and the
  tool keeps offering each task until all three are in (WORK_PLAN C42). Don't discuss a test task
  with anyone before all of you have decided.
- Work in **batches of 25** with a break between batches.
- Don't approve to save time. A reject or fix with a clear note is worth as much as an approval.
- If the reject rate goes above 30%, the drafting is fixed. The bar for approval stays the same.

## Order of work (ASK_ME R1, decided 2026-11-25)

Review in queue order at the current pace: **blind ratings first** (`rate-next`, below), then the
queue in the priority order of the table below, in which the test-task correctness pass comes
right after the calibration and R5 batches. No extra reviewer hours.

With 3 reviewers instead of 4 the review takes longer. R1's figure was ~1,000 reviews at
4 × ~25 = ~100 a day, about 10 working days. At 3 × ~25 = ~75 a day that becomes about 13–14
working days. With the R5 re-review and EIH-Fresh back at ~150 (`docs/SCHEDULE.md` §4, ~1,250
reviews) it is about **17 working days**. These are **estimates**, re-set from the measured minutes
per review after day one.

## Day one (calibration)

All three of you review the **same 10 tasks** (batch `calibration-01`) on your own, without
talking about them. We measure how often you agree: Cohen's kappa for each pair and **Fleiss'
kappa over the 3 raters** (`python scripts/review.py kappa calibration-01`). This number goes in
the paper. After everyone has finished, we discuss the disagreements.

## Independent re-review of the pilot tasks (ASK_ME R5, decided 2026-11-25)

The 44 pilot tasks marked `human_approved_by: "lead_researcher"` were approved by the three of you
**jointly**. A joint approval is not an independent one, so each of you re-reviews all 44 on your
own: the 10 in `calibration-01`, the 10 in `r5-independent-01` and the 24 test tasks in
`test-correctness-01..04`. Agreement is Fleiss' kappa over 3 raters.

Stay blind until all three of you have finished a batch. The six R5 batches (`calibration-01`,
`r5-independent-01`, `test-correctness-01..04`) carry `reviews_required: 3`, and for them the tool
(WORK_PLAN C42):

- offers every task to each of you until all three decisions are in, whatever the others decided;
- takes **one** decision per person per task (no second decision, no fourth reviewer);
- after your decision says only "in blind review", never the task's outcome; `review.py next`
  shows how many reviews a task has, never what anyone decided;
- shows these tasks as `in_blind_review` in `review.py report`, and refuses `review.py kappa` on a
  batch until every task in it has its three reviews.

The decisions are still plain files in git, so do not open `benchmark/data/review/decisions/`
(or anyone's `.jsonl` there) before all three of you have finished. `human_approved_by` on these
tasks is updated only after the re-review (`docs/benchmark.md` §2).

## What is in the queue (served in this order)

`python scripts/review.py next --reviewer <name>` gives you the highest-priority item you may
decide on:

| Priority | Batch | What you check |
|---|---|---|
| 10 | `calibration-01` | Day-one agreement: all three of you, same 10 tasks (also R5) |
| 12 | `r5-independent-01` | R5: 10 pilot dev/val tasks, each reviewed by all three of you, blind |
| 20 | `labels-L1-01/02` | Retrieval labels: do the shown lines contain the evidence needed for the answer? (`evidence_correct`) |
| 25 | `audit-fixes-01` | Proposed fixes to 20 dev/val tasks (`docs/BENCHMARK_AUDIT.md`). Approve only if the corrected task is right against the shown lines |
| 15 | `test-correctness-01..04` | The 24 held-out test tasks, at least two different reviewers each (all three under R5), before any tuning |
| 50 | `draft-*` | New tasks drafted by Claude: never approve one you requested |

## Test-task fixes

If a test task is wrong, use `fix` and write the correction in the note: exact file and lines
(e.g. `src/flask/app.py L966-1090`) plus the corrected answer. Claude does not read test tasks. A
person, not Claude, turns your note into a proposal, and two *other* reviewers must approve it.

## Blind answer rating (M1)

These 40 answers decide how answer correctness is measured. You never see which system wrote an
answer, and you should not try to guess (some never cite files).

```
python scripts/review.py rate-next --reviewer <name>
python scripts/review.py rate <H0xx> --reviewer <name> --correctness 1-5 --completeness 1-5 --accept yes|no
```

| Field | Question to ask |
|---|---|
| correctness | Does it state the reference's key facts without contradicting the shown code? |
| completeness | Does it cover everything the reference needs? |
| accept | Would you accept it as a correct answer? Extra correct detail is fine |

Each answer is rated by two different people. With three raters that is 27, 25 and 28 answers
(Avaneesh, Sanvi, Aryan), reassigned with seed 42 on 2026-11-25.

**Rating is blocked until the batch's key is verified** (WORK_PLAN C42). The key (which system
wrote each answer) is kept outside the repository by a key holder, never on a rater's machine.
The key holder runs, once per batch:

```
python scripts/review.py verify-key --batch <batch> --key <path to the key file>
```

This checks the key against the checksum in the batch file and stores only a timestamp
(`key_verified_at`). Until then `rate-next` shows nothing and `rate` is refused. Raters never need
the key. For `m1-rating-01` the key is not yet recovered: see `ASK_ME.md` K1/K2.
