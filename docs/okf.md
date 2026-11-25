# OKF knowledge layer (Open Knowledge Format)

EIH stores shared, portable knowledge as **OKF bundles**, the open format Google Cloud
published in its `knowledge-catalog` repository
(<https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf>, Apache-2.0).
The specification there is **OKF v0.2** (v0.2 supersedes v0.1). EIH writes v0.2 and reads
v0.1 bundles through the spec's own fallbacks (§13). This is an **application feature**
(WORK_PLAN step 24a, change C33). It is not one of the research Systems A–E.

## 1. What a bundle is

A directory of Markdown files. Each non-reserved `.md` file is one **concept**: YAML
frontmatter plus a Markdown body. Its id is its path without `.md`. `index.md` and `log.md`
are reserved at every level. `type` is the only required field. Links between concepts are
ordinary Markdown links (`[orders](/tables/orders.md)` or relative). A bundle needs no EIH
code to read: `cat` or any Markdown viewer works.

| Field (frontmatter) | Meaning in EIH |
|---|---|
| `type` | required; e.g. `Python Module`, `Repository`, `API Endpoint`, `Project Document`, `Playbook` |
| `title`, `description`, `resource`, `tags` | optional, shown in the explorer and search |
| `generated: {by, at}` | who wrote the current text: `human:<id>`, `eih_agent/<model>`, `eih_okf_producer/0.1` |
| `verified: [{by, at}]` | who confirmed it; gives the trust tier (unverified / machine-confirmed / human-reviewed) |
| `status` | `draft` / `stable` / `deprecated` |
| `stale_after`, `sources` | freshness and provenance, used as-is |
| anything else | kept unchanged on round-trip (EIH's own extra key is `eih:`) |

## 2. Human ↔ agent workflow

```
person (UI) ──edit──────────────► bundle files ◄──approve── person (Review page)
     │                                │  ▲                          ▲
     └─ask──► EIH agent ──reads───────┘  │                          │
                 │                       └── nothing written ───────┘
                 └─files proposals (pending) ─────────────────────► Review queue
```

1. A person asks a question in **Chat**. The agent searches the bundle (semantic via Qdrant;
   lexical if Qdrant is down, and says so), follows links one hop, adds code evidence from the
   research corpus (System B's fixed hybrid retrieval, read-only), and answers with
   `[okf:<id>]` / `[code:n]` citations. Citations to anything it was not given are reported
   as **invalid**.
2. If the agent finds missing, outdated or conflicting knowledge, it files a **proposal**
   (create / update / deprecate) with its rationale, the evidence it used and the content hash
   of the concept it read. Proposals are stored outside the bundle
   (`okf_bundles/.eih_state/<bundle>/proposals/`).
3. A person reviews it on the **Review** page. They see a diff of current versus proposed text
   and can approve it, edit it and then approve, or reject it with a reason. Only `human:<id>`
   actors can approve or edit; the API refuses an agent actor.
4. On approval the concept is written with `generated.by` set to the agent (or to the reviewer
   if they edited it) and `verified` set to the reviewer. `log.md` and the indexes are updated,
   the audit trail records the approval, and the concept is re-indexed in Qdrant and Neo4j.
5. **No silent overwrite.** If the concept changed after the agent read it, approval is refused
   as a `conflict` and nothing is written. Direct human edits use the same check (HTTP 409).

People can also browse, search, create and edit concepts directly on the **Knowledge** page,
and import or export whole bundles as a zip.

## 3. Where it lives in the code

| Module | Role |
|---|---|
| `knowledge/okf/document.py` | parse/serialize (timestamps kept as written), validation, trust tiers, staleness |
| `knowledge/okf/bundle.py` | discovery, link resolution, conformance report, search, `index.md` and `log.md` |
| `knowledge/okf/collaboration.py` | proposals, approve/reject/edit, optimistic concurrency, audit, change listeners |
| `knowledge/okf/producer.py` | deterministic bundle from wave-1 code (AST), the API contract and project docs |
| `knowledge/okf/sync.py` | Qdrant collection `eih_okf` and Neo4j `:OKFConcept` / `OKF_LINKS_TO` / `OKF_DESCRIBES` |
| `knowledge/okf/agent.py` | grounded answers, link following, citation check, gap proposals |
| `apps/api/routers/okf.py`, `chat.py` | HTTP API; `web/src/pages/KnowledgePage.tsx`, `ReviewPage.tsx`, `ChatPage.tsx` |

**Isolation from the research data.** OKF never writes to `eih_knowledge_v2`. Its Neo4j nodes
are not `:Entity`. The research edge count and the graph reset are scoped to `:Entity`, so the
manifest's graph identity (37,066 / 58,982) is unchanged by the OKF projection. This was
checked live on 2026-11-23: 62,704 relationships in the database, of which 58,982 are
research edges.

## 4. Commands

```powershell
python -m scripts.okf_produce produce                 # build/refresh okf_bundles/eih and index it
python -m scripts.okf_produce validate path\to\bundle # conformance report for any bundle
python -m scripts.okf_produce import path\to\bundle --name other
python -m scripts.okf_produce sync --bundle eih       # full re-projection into Qdrant + Neo4j
```

The producer only rewrites concepts it wrote itself (`generated.by` = `eih_okf_producer/…`).
It never overwrites a concept a person wrote or approved.

## 5. Conformance and tests

`tests/test_knowledge/test_okf.py` checks the spec section by section: required `type`,
optional and unknown fields, round-trip stability, trust tiers including the bare `verified`
mapping, staleness, v0.1 `timestamp`, links (absolute, relative, in code fences, broken,
escaping the bundle), reserved files, index frontmatter, log date headings, and versioning.
Two of Google's own sample bundles (`acme_retail`, `crypto_bitcoin`, vendored under
`tests/test_knowledge/fixtures/okf_external/` with their licence) are consumed as external
bundles. All four upstream samples (53 concepts) were also checked on 2026-11-22: all
conformant, 0 broken links, round-trip stable. The collaboration rules, producer, sync (one
live integration test against Qdrant and Neo4j), agent and HTTP API have their own tests.

## 6. Limits

- There is no login. The `human:<id>` you type in the UI is trusted, which suits a single-user
  local app bound to `127.0.0.1`. Put authentication in front before exposing it on a network.
- Bundles are data under `okf_bundles/` (gitignored). Keep a hand-edited bundle in its own git
  repository; OKF §3 recommends git for history and diffs.
- Attested Computation concepts (§10) are read, shown and validated, but EIH does not execute
  their executors or attesters. Running attesters needs their runtimes, such as BigQuery.
