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
