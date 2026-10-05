# Retrieval energy per query, by component (retrieval-energy-2026-10-05)

36 dev/val queries x 5 repeats per window; idle 4.26 W (measured over 30 s, same counter-only method). GPU gross MEASURED, GPU net DERIVED, CPU ESTIMATED (TDP x utilisation).

| Component | ms/query | GPU gross J/query | GPU net J/query | CPU J/query (est.) |
|---|---|---|---|---|
| embed_query | 10.4 | 0.432 | 0.388 | 0.097 |
| dense_search | 22.1 | 0.208 | 0.114 | 0.172 |
| bm25 | 410.6 | 1.380 | -0.370 | 3.348 |
| rerank_top30 | 126.4 | 9.261 | 8.722 | 1.171 |
| esc2_without_graph | 505.7 | 7.493 | 5.338 | 4.587 |
| baseline_b | 467.3 | 2.256 | 0.265 | 3.985 |
| system_c | 416.7 | 4.843 | 3.068 | 3.845 |
| system_d | 413.6 | 4.907 | 3.145 | 3.331 |
| system_e_esc1 | 447.2 | 6.136 | 4.230 | 3.934 |
| system_e_esc2 | 582.0 | 8.381 | 5.901 | 5.645 |
| system_e_esc_max | 743.3 | 22.034 | 18.867 | 7.270 |
| graph_increment | 76.3 | 0.888 | 0.563 | 1.058 |

`graph_increment` = system_e_esc2 minus the same rung with graph context switched off.
Cooling events: none.
