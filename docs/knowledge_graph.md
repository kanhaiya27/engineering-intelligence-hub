# Engineering Knowledge Graph Foundation

## Overview

The Engineering Knowledge Graph provides structured relational context across repository code entities and software engineering lifecycle artifacts. It connects abstract syntax tree (AST) components (modules, classes, functions, methods, tests) with version control entities (commits, pull requests, issues, architecture decisions, and incident reports).

```
                      ┌────────────────┐
                      │   Repository   │
                      └───────┬────────┘
                              │ CONTAINS
          ┌───────────────────┼───────────────────┐
          ↓                   ↓                   ↓
     ┌──────────┐        ┌──────────┐        ┌──────────┐
     │   File   │        │  Commit  │        │  Issue   │
     └────┬─────┘        └────┬─────┘        └────┬─────┘
          │ CONTAINS          │ MODIFIES          │ RESOLVED_BY
          ↓                   ↓                   │
     ┌──────────┐        ┌──────────┐             │
     │  Module  │        │   File   │◄────────────┘
     └────┬─────┘        └──────────┘
          │ CONTAINS
     ┌────┴─────┐
     ↓          ↓
┌─────────┐ ┌──────────┐
│  Class  │ │ Function │
└────┬────┘ └────┬─────┘
     │ CONTAINS  │ CALLS / TESTED_BY
     ↓           ↓
┌─────────┐ ┌──────────┐
│ Method  │ │   Test   │
└─────────┘ └──────────┘
```

> [!IMPORTANT]
> **Research Note:** This milestone establishes a knowledge graph foundation; it does not yet demonstrate that graph retrieval improves answer quality or efficiency. That hypothesis is evaluated in subsequent milestones (M3 and M5).

---

## 1. Schema & Node Types

| Node Label | Description | Identity Key Pattern | Mandatory Provenance Attributes |
|---|---|---|---|
| `Repository` | Root repository node | `repo:{repo}` | `repository`, `commit_sha`, `url` |
| `File` | Ingested source or documentation file | `file:{repo}:{commit}:{source_path}` | `repository`, `commit_sha`, `source_path`, `artifact_id`, `line_count`, `language` |
| `Module` | Python module namespace | `module:{repo}:{commit}:{module_name}` | `repository`, `commit_sha`, `source_path`, `symbol_name`, `artifact_id` |
| `Class` | Class definition extracted from AST | `class:{repo}:{commit}:{source_path}:{class_name}` | `repository`, `commit_sha`, `source_path`, `symbol_name`, `start_line`, `end_line` |
| `Function` | Top-level function | `func:{repo}:{commit}:{source_path}:{func_name}:{start_line}` | `repository`, `commit_sha`, `source_path`, `symbol_name`, `start_line`, `end_line`, `is_async` |
| `Method` | Class method | `method:{repo}:{commit}:{source_path}:{class_name}:{method_name}:{start_line}` | `repository`, `commit_sha`, `source_path`, `symbol_name`, `class_name`, `start_line`, `end_line` |
| `Test` | Test function or test method | `test:{repo}:{commit}:{source_path}:{test_name}:{start_line}` | `repository`, `commit_sha`, `source_path`, `symbol_name`, `start_line`, `end_line` |
| `Commit` | Git commit record | `commit:{repo}:{sha}` | `repository`, `commit_sha`, `author`, `message`, `committed_at`, `lines_added`, `lines_deleted` |
| `PullRequest` | GitHub / Git pull request | `pr:{repo}:{pr_number}` | `repository`, `pr_number`, `title`, `author`, `merged_at`, `merge_commit_sha` |
| `Issue` | GitHub issue report | `issue:{repo}:{issue_number}` | `repository`, `issue_number`, `title`, `author`, `labels` |
| `ArchitectureDecision` | ADR document | `adr:{repo}:{decision_id}` | `repository`, `decision_id`, `title`, `status`, `source_path` |
| `Incident` | Incident / postmortem document | `incident:{repo}:{incident_id}` | `repository`, `incident_id`, `title` |

---

## 2. Canonical Relationships

- `Repository -[:CONTAINS]-> File | Commit | Issue | PullRequest | ArchitectureDecision`
- `File -[:CONTAINS]-> Module`
- `Module -[:CONTAINS]-> Class | Function`
- `Module -[:IMPORTS]-> Module`
- `Module -[:DEPENDS_ON]-> Module`
- `Class -[:CONTAINS]-> Method`
- `Function -[:CALLS]-> Function`
- `Function / Method -[:TESTED_BY]-> Test`
- `Issue -[:RESOLVED_BY]-> Commit`
- `Issue -[:LINKED_TO]-> PullRequest`
- `PullRequest -[:MODIFIES]-> File`
- `Commit -[:MODIFIES]-> File`
- `ArchitectureDecision -[:AFFECTED]-> File`

---

## 3. Provenance & Identity Strategy

All graph entities preserve strict lineage back to repository source code:
1. **Idempotent Identifiers:** Deterministic keys based on repository name, commit SHA, file path, symbol name, and line ranges ensure idempotent construction without duplicate nodes.
2. **Line-Number Precision:** AST entity extraction captures 1-indexed `start_line` and `end_line` offsets.
3. **No Unverifiable Facts:** Relationships are constructed strictly when explicit AST syntax (imports, calls, class hierarchies) or version control metadata (commit diffs, issue resolution links) confirms them.

---

## 4. Graph Stores

- **`Neo4jGraphStore`** (`knowledge/graph/neo4j.py`): Concrete production store connecting via Bolt protocol (`bolt://localhost:7687`), managing uniqueness constraints and parameterized Cypher queries.
- **`InMemoryGraphStore`** (`knowledge/graph/in_memory.py`): Fast, lightweight graph implementation for deterministic unit testing without external database dependencies.

---

## 5. Query Interface & REST API

The graph store exposes query utilities in `knowledge/graph/queries.py`:
- `get_entity(store, node_id)`
- `get_neighborhood(store, node_id, direction, max_depth)`
- `find_dependencies(store, module_id)`
- `find_related_files(store, file_id)`
- `find_issue_commits(store, issue_id)`
- `find_modified_files(store, commit_id)`
- `get_subgraph(store, root_id, max_depth)`

REST Endpoints:
- `GET /graph/health`: Health status, node count, and edge count.
- `GET /graph/entity/{node_id}`: Entity properties and label.
- `GET /graph/neighbors/{node_id}`: Neighboring nodes and connecting relationships.
