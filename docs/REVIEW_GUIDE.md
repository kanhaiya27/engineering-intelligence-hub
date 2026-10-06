# Reviewer guide: checking benchmark tasks

For: Avaneesh, Sanvi, Aayan, Radhesh. About 3 hours a day until 12 Oct.

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
- Test-split tasks are each checked by **two different people**, independently. Don't discuss
  a test task with the other reviewer before you have both decided.
- Work in **batches of 25** with a break between batches.
- Don't approve to save time. A reject or fix with a clear note is worth as much as an approval.
- If the reject rate goes above 30%, the drafting is fixed. The bar for approval stays the same.

## Day one (calibration)

All four of you review the **same 10 tasks** (batch `calibration-01`) on your own, without
talking about them. We measure how often you agree (Cohen's kappa). This number goes in the
paper. After everyone has finished, we discuss the disagreements.

## What is in the queue (served in this order)

`python scripts/review.py next --reviewer <name>` gives you the highest-priority item you may
decide on:

| Priority | Batch | What you check |
|---|---|---|
| 10 | `calibration-01` | Day-one agreement: all four of you, same 10 tasks |
| 20 | `labels-L1-01/02` | Retrieval labels: do the shown lines contain the evidence needed for the answer? (`evidence_correct`) |
| 25 | `audit-fixes-01` | Proposed fixes to 20 dev/val tasks (`docs/BENCHMARK_AUDIT.md`). Approve only if the corrected task is right against the shown lines |
| 30 | `test-correctness-01..04` | The 24 held-out test tasks, two different reviewers each, before any tuning |
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

Each of you rates 20 answers, and each answer is rated by two of you.
