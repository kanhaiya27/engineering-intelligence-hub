# M1 protocol: choosing the correctness measure (pre-registered)

Written and committed **before any rating exists** (2026-10-06). It is approved by Avaneesh (Step 3 decision M1).

**Why.** Plain token F1 between long answers and short references never reached a task threshold
(0 of 648 dev/val trials). The correctness yardstick is replaced by the measure that agrees best with
human judgement. It is chosen before any system-level comparison.

## Data

- **Ratings.** 40 blind answers (`benchmark/data/review/rating/m1-rating-01.json`).
  - They are non-refusal, trial-0 answers from the Step 2c dev/val run, spread over SDLC stage × system
    (seed 42).
  - 9 tasks whose question or reference answer has a proposed fix are excluded, decided from the audit
    alone before any rating.
- **Raters.** Each answer is rated by 2 of the 4 reviewers (rotating pairs). Raters see:
  - the question;
  - the reference answer;
  - the answer;
  - the labelled evidence lines.

  They never see the system, trial or any score.
- **Key.** The blind-id → task/system key is stored outside git (`C:/EIH_backups/`). Its sha256 is in the
  batch file. The selection code reads only task ids from it, never system ids.
- **Ratings recorded:** correctness 1–5, completeness 1–5, accept yes/no.

## Human targets

- **Continuous:** mean correctness of the two raters (1–5).
- **Binary ("human-correct"):** both raters accept.
- **Inter-rater agreement is reported first:**
  - quadratic-weighted Cohen's kappa on correctness;
  - Cohen's kappa on accept.

## Candidate measures (computed per answer, maximum over the reference and its alternatives)

| Measure | Definition | Note |
|---|---|---|
| `token_f1` | Set-based token F1 (current measure, no ×1.5) | Reported alongside whatever is chosen |
| `ref_recall` | Share of the reference's content tokens (lower-case words of ≥ 3 characters, stop-words removed) found in the answer | Does not penalise extra correct detail |
| `semantic` | Cosine similarity of BGE-small-en-v1.5 embeddings, answer vs reference | 512-token window: long answers are truncated |
| `llm_judge` | The local 7B asked whether the answer states the reference's key facts without contradicting them (YES = 1, NO = 0) | **The judge is the evaluated model: self-preference risk**, disclosed whatever the outcome |

## Selection rule (fixed now)

1. **Primary:** Spearman ρ between the measure and mean human correctness, over the 40 answers. Each ρ
   gets a 95% bootstrap CI (10,000 resamples, seed 42). The measure with the highest ρ is chosen.
2. **Threshold:** the cut-off *t* that maximises Cohen's kappa between (measure ≥ *t*) and
   human-correct. Every observed value is scanned. When several values tie, the midpoint of the best
   range is taken. The kappa and its bootstrap CI are reported.
3. **Report:** ρ, kappa and the agreement table for **every** candidate, plus inter-rater agreement.
4. **Order:** the selection result (measure, threshold, all agreement numbers) is committed **before**
   any system is rescored with it. No measure or threshold may be chosen because it makes a system
   look better. The selection script computes no per-system numbers.
5. **Then (one change set):** the chosen measure and threshold, the verified audit fixes and the
   verified label changes are applied together. Dev/val is rerun once and the config re-frozen
   (WORK_PLAN C29).

## Limits stated in advance

- 40 answers with 2 raters each give a modest sample. CIs will be wide and are reported.
- **Answer style can hint at the system.** System A never cites files. Raters are told not to guess.
- **These are dev/val answers.** The threshold is set on dev/val (allowed) and is never re-tuned on test.
