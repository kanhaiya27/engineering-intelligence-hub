# Citation audit — references of the original plan (`docs/original_plan.md` §14)

Checked 2026-10-05 against the sources linked below. Rule: every citation must be real and
traceable; anything not confirmed is flagged, and **no replacement is invented**.
`docs/original_plan.md` stays frozen; corrections go into the paper/report text.

| Ref | Status | What was confirmed | Action needed |
|---|---|---|---|
| [1] Pan et al., "Towards Automatically Optimizing Retrieval Augmented AI Systems" | ✅ Verified | Authors M. Z. Pan, N. Arabzadeh, M. Jacob, F. Kazhamiaka, E. Choukse, M. A. Zaharia; **NeurIPS 2025 Workshop: ML for Systems**. Abstract: "configurations within ≤3% accuracy that differ by up to 20.2× in energy"; Llama3-8B + stronger retriever matches Llama3-70B "using over 5× less energy" — [neurips.cc/virtual/2025/129100](https://neurips.cc/virtual/2025/129100) | Add venue (plan says only "OpenReview") |
| [2] "On the Effectiveness of Proposed Techniques to Reduce Energy Consumption in RAG Systems: A Controlled Experiment" | ⚠ Partly verified | Authors Z. Guo, C. Gao, J. Bogner; arXiv:2601.02522; accepted at **ICSE-SEIS'26** (Software Engineering in Society track); up to 60% energy reduction, up to 30% accuracy drop — [arxiv.org/abs/2601.02522](https://arxiv.org/abs/2601.02522v2) | Venue is ICSE-**SEIS**, not the main track. **DOI 10.1145/3786581.3786932 not confirmed** (arXiv lists only 10.48550/arXiv.2601.02522) — verify in the ACM DL before citing it |
| [3] CodeRepoQA (arXiv:2412.14764; SIGIR 2025) | Verified 2026-08-26 (report) | not re-checked today | — |
| [4] StackRepoQA (arXiv:2603.26567) | Verified 2026-08-26 (report) | not re-checked today | — |
| [5] OpenAI, SWE-bench Verified | ⚠ Mostly verified | Published 23 Feb 2026; official title "Why SWE-bench Verified no longer measures frontier coding capabilities" (URL slug: why-we-no-longer-evaluate-swe-bench-verified); "at least 59.4% of audited problems" flawed; recommends SWE-bench Pro — [openai.com](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/) | Use the official title; "138 hard tasks" not confirmed in this check — re-read the post before citing that number |
| [6] SWE-Bench Pro (arXiv:2509.16941) | Verified 2026-08-26 (report) | not re-checked today | — |
| [7] SWE-rebench (arXiv:2505.20411) | Verified 2026-08-26 (report) | not re-checked today | — |
| [8] Multi-SWE-bench (arXiv:2504.02605) | Verified 2026-08-26 (report) | not re-checked today | — |
| [9] "A Survey of Energy Concerns for Software Engineering", JSS 2024 | ❌ **Not found** | No publication with this title found | Team must supply the exact citation (authors, volume, DOI) or remove it |
| [10] "Sustainability in the Field of Software Engineering: A Tertiary Study", TOSEM 2026 | ❌ **Not found** | No publication with this title found | Team must supply the exact citation or remove it |
| [11] "Green Artificial Intelligence: A Comprehensive Review of Metrics, Tools, Challenges, Trends, and Future Prospects" | ✅ Verified | P. Peykani, A. Emrouznejad, S. Ghanidel, I. Javadi-Sisi, S. Mirjalili; Archives of Computational Methods in Engineering, 2026 — [doi.org/10.1007/s11831-026-10546-2](https://link.springer.com/article/10.1007/s11831-026-10546-2) | Add authors and DOI |
| [12] "Efficient and Green Large Language Models for Software Engineering: Literature Review, Vision, and the Road Ahead" | ✅ Verified | J. Shi, Z. Yang, D. Lo; ACM TOSEM 34(5); arXiv:2404.04566 — [arxiv.org/abs/2404.04566](https://arxiv.org/pdf/2404.04566) | Add authors and venue |
| [13] AutoRAG (arXiv:2410.20878) | ✅ Verified | D. Kim, B. Kim, D. Han, M. Eibich — [arxiv.org/abs/2410.20878](https://arxiv.org/abs/2410.20878) | — |
| [14] The ML.ENERGY Benchmark (arXiv:2505.06371) | ✅ Verified | J.-W. Chung et al. — [arxiv.org/abs/2505.06371](https://arxiv.org/abs/2505.06371) | — |
