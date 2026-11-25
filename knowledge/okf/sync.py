"""
Project an OKF bundle into Qdrant (semantic search) and Neo4j (link graph).

The markdown bundle stays the source of truth; both projections are derived, rebuildable
at any time from the files, and updated incrementally when concepts change
(``KnowledgeWorkspace.on_change``).

Isolation from the research data (WORK_PLAN C21, C33):

* Qdrant: OKF goes to its own collection (``settings.okf.collection_name``, default
  ``eih_okf``). The research collection ``eih_knowledge_v2`` is never written.
* Neo4j: concepts are ``:OKFConcept`` nodes (never ``:Entity``) joined by ``OKF_LINKS_TO``.
  A concept whose ``resource`` names a file of an indexed repository at the pinned commit
  gets an ``OKF_DESCRIBES`` edge to that ``:File`` node. Research counts only
  ``:Entity``-to-``:Entity`` edges and the graph reset only deletes ``:Entity`` nodes, so the
  projection changes neither.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.logging import get_logger
from knowledge.okf.bundle import Concept, OKFBundle

logger = get_logger(__name__)

_NS = uuid.UUID("6b1f3c8e-0d55-4f0e-9a51-0c4a7f2b9e11")  # fixed namespace: stable point ids
_HEADING_RX = re.compile(r"^#{1,6}\s")
_GITHUB_BLOB_RX = re.compile(r"^https://github\.com/([^/]+/[^/]+)/blob/([0-9a-f]{7,40})/(.+?)(?:#.*)?$")
MAX_TOKENS = 480  # below BGE-small's 512 including the title header and special tokens


@dataclass
class OKFChunk:
    point_id: str
    text: str
    payload: Dict[str, Any]


def _sections(body: str) -> List[Tuple[str, str]]:
    """Split a body at headings (outside code fences): [(heading, text)]."""
    out: List[Tuple[str, List[str]]] = [("", [])]
    fence = False
    for line in body.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        if not fence and _HEADING_RX.match(line):
            out.append((line.lstrip("#").strip(), [line]))
        else:
            out[-1][1].append(line)
    return [(h, "\n".join(ls).strip()) for h, ls in out if "\n".join(ls).strip()]


def _fit(text: str, budget: int, count) -> List[str]:
    """Split text into pieces of at most `budget` tokens (paragraphs, then lines, then words)."""
    if count(text) <= budget:
        return [text]
    pieces: List[str] = []
    for sep in ("\n\n", "\n", " "):
        parts = text.split(sep)
        if len(parts) == 1:
            continue
        cur = ""
        for part in parts:
            cand = f"{cur}{sep}{part}" if cur else part
            if count(cand) <= budget:
                cur = cand
                continue
            if cur:
                pieces.append(cur)
            if count(part) <= budget:
                cur = part
            else:
                pieces.extend(_fit(part, budget, count))
                cur = ""
        if cur:
            pieces.append(cur)
        return pieces
    # one unbreakable token run: hard cut by characters
    step = max(1, len(text) * budget // max(1, count(text)))
    return [text[i:i + step] for i in range(0, len(text), step)]


def concept_chunks(bundle_name: str, c: Concept, count=None) -> List[OKFChunk]:
    """Embedding chunks for one concept: one per section, each under the token budget."""
    if count is None:
        from ingestion.processors.chunker import estimate_tokens as count
    doc = c.doc
    header = f"{c.title} ({doc.type})" + (f": {doc.description}" if doc.description else "")
    base = {
        "bundle": bundle_name, "concept_id": c.id, "title": c.title, "type": doc.type,
        "description": doc.description, "tags": doc.tags, "status": doc.status,
        "trust_tier": doc.trust_tier, "stale": doc.is_stale(), "generated_by": doc.generated_by,
        "resource": doc.frontmatter.get("resource"), "content_hash": doc.content_hash(),
    }
    sections = _sections(doc.body) or [("", "")]
    out: List[OKFChunk] = []
    for s_idx, (heading, text) in enumerate(sections):
        budget = MAX_TOKENS - count(header) - 4
        for p_idx, piece in enumerate(_fit(text, max(64, budget), count) if text else [""]):
            full = f"{header}\n\n{piece}".strip()
            pid = str(uuid.uuid5(_NS, f"{bundle_name}::{c.id}::{s_idx}::{p_idx}"))
            out.append(OKFChunk(pid, full, dict(base, section=heading, section_index=s_idx, part=p_idx, text=full)))
    return out


class OKFVectorIndex:
    """OKF concepts in their own Qdrant collection."""

    def __init__(self, collection: Optional[str] = None, embedder=None, client=None):
        from core.config import settings

        self.collection = collection or settings.okf.collection_name
        if self.collection == settings.vector_store.collection_name:
            raise ValueError("the OKF collection must not be the research collection")
        self._embedder = embedder
        self._client = client
        self._dim = settings.vector_store.embedding_dimension

    @property
    def client(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            from core.config import settings
            self._client = QdrantClient(host=settings.vector_store.host, port=settings.vector_store.port)
        return self._client

    @property
    def embedder(self):
        if self._embedder is None:
            from knowledge.vector.embeddings import BGEEmbeddingModel
            self._embedder = BGEEmbeddingModel()
        return self._embedder

    def ensure_collection(self) -> None:
        from qdrant_client import models as qm

        if not self.client.collection_exists(self.collection):
            self.client.create_collection(self.collection, vectors_config=qm.VectorParams(
                size=self._dim, distance=qm.Distance.COSINE))
            for field, schema in (("bundle", qm.PayloadSchemaType.KEYWORD),
                                  ("concept_id", qm.PayloadSchemaType.KEYWORD),
                                  ("type", qm.PayloadSchemaType.KEYWORD)):
                self.client.create_payload_index(self.collection, field, field_schema=schema)

    def _filter(self, bundle: str, concept_ids: Optional[List[str]] = None):
        from qdrant_client import models as qm

        must = [qm.FieldCondition(key="bundle", match=qm.MatchValue(value=bundle))]
        if concept_ids is not None:
            must.append(qm.FieldCondition(key="concept_id", match=qm.MatchAny(any=concept_ids)))
        return qm.Filter(must=must)

    def sync_concepts(self, bundle: OKFBundle, bundle_name: str, concept_ids: Iterable[str]) -> Dict[str, int]:
        """Replace the points of these concepts (deleted concepts just lose their points)."""
        from qdrant_client import models as qm

        ids = sorted(set(concept_ids))
        self.ensure_collection()
        self.client.delete(self.collection, points_selector=qm.FilterSelector(filter=self._filter(bundle_name, ids)),
                           wait=True)
        chunks = [ch for cid in ids if (c := bundle.get(cid)) for ch in concept_chunks(bundle_name, c)]
        self._upsert(chunks)
        return {"concepts": len(ids), "points": len(chunks)}

    def sync_bundle(self, bundle: OKFBundle, bundle_name: str) -> Dict[str, int]:
        from qdrant_client import models as qm

        self.ensure_collection()
        self.client.delete(self.collection, points_selector=qm.FilterSelector(filter=self._filter(bundle_name)),
                           wait=True)
        chunks = [ch for c in bundle.concepts.values() for ch in concept_chunks(bundle_name, c)]
        self._upsert(chunks)
        return {"concepts": len(bundle.concepts), "points": len(chunks)}

    def _upsert(self, chunks: List[OKFChunk], batch: int = 256) -> None:
        from qdrant_client import models as qm

        for i in range(0, len(chunks), batch):
            part = chunks[i:i + batch]
            vectors = self.embedder.embed_batch([c.text for c in part])
            self.client.upsert(self.collection, wait=True, points=[
                qm.PointStruct(id=c.point_id, vector=v, payload=c.payload) for c, v in zip(part, vectors)])

    def search(self, query: str, bundle: Optional[str] = None, limit: int = 8) -> List[Dict[str, Any]]:
        if not self.client.collection_exists(self.collection):
            return []
        vec = self.embedder.embed_text(query)
        res = self.client.query_points(self.collection, query=vec, limit=limit, with_payload=True,
                                       query_filter=self._filter(bundle) if bundle else None)
        return [dict(p.payload or {}, score=float(p.score)) for p in res.points]

    def count(self, bundle: Optional[str] = None) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        return self.client.count(self.collection, count_filter=self._filter(bundle) if bundle else None,
                                 exact=True).count


class OKFGraphProjection:
    """OKF concepts as :OKFConcept nodes and OKF_LINKS_TO edges in Neo4j."""

    def __init__(self, store=None):
        if store is None:
            from knowledge.graph.neo4j import Neo4jGraphStore
            store = Neo4jGraphStore()
        self.store = store

    def _run(self, cypher: str, **params) -> List[Dict[str, Any]]:
        return self.store.query(cypher, params)

    def ensure_schema(self) -> None:
        self._run("CREATE CONSTRAINT okf_concept_key IF NOT EXISTS FOR (c:OKFConcept) REQUIRE c.key IS UNIQUE")

    @staticmethod
    def _props(bundle_name: str, c: Concept) -> Dict[str, Any]:
        d = c.doc
        return {"key": f"{bundle_name}::{c.id}", "bundle": bundle_name, "concept_id": c.id, "title": c.title,
                "type": d.type, "description": d.description, "tags": d.tags, "status": d.status,
                "trust_tier": d.trust_tier, "generated_by": d.generated_by or "",
                "resource": str(d.frontmatter.get("resource") or ""), "content_hash": d.content_hash()}

    def sync_concepts(self, bundle: OKFBundle, bundle_name: str, concept_ids: Iterable[str]) -> Dict[str, int]:
        ids = sorted(set(concept_ids))
        self.ensure_schema()
        keys = [f"{bundle_name}::{cid}" for cid in ids]
        present = [self._props(bundle_name, c) for cid in ids if (c := bundle.get(cid))]
        gone = [k for k, cid in zip(keys, ids) if bundle.get(cid) is None]
        if gone:
            self._run("MATCH (c:OKFConcept) WHERE c.key IN $keys DETACH DELETE c", keys=gone)
        if present:
            self._run("UNWIND $rows AS r MERGE (c:OKFConcept {key: r.key}) SET c += r", rows=present)
            self._run("MATCH (c:OKFConcept)-[r:OKF_LINKS_TO|OKF_DESCRIBES]->() WHERE c.key IN $keys DELETE r",
                      keys=[p["key"] for p in present])
        touched = set(ids)
        edges = [(a, b) for a, b in bundle.concept_edges() if a in touched or b in touched]
        self._write_edges(bundle_name, edges)
        self._write_describes(bundle_name, [c for cid in ids if (c := bundle.get(cid))])
        return {"concepts": len(present), "removed": len(gone), "edges": len(edges)}

    def sync_bundle(self, bundle: OKFBundle, bundle_name: str) -> Dict[str, int]:
        self.ensure_schema()
        self._run("MATCH (c:OKFConcept {bundle: $b}) DETACH DELETE c", b=bundle_name)
        rows = [self._props(bundle_name, c) for c in bundle.concepts.values()]
        for i in range(0, len(rows), 1000):
            self._run("UNWIND $rows AS r MERGE (c:OKFConcept {key: r.key}) SET c += r", rows=rows[i:i + 1000])
        edges = bundle.concept_edges()
        self._write_edges(bundle_name, edges)
        described = self._write_describes(bundle_name, list(bundle.concepts.values()))
        return {"concepts": len(rows), "edges": len(edges), "describes": described}

    def _write_edges(self, bundle_name: str, edges: List[Tuple[str, str]]) -> None:
        rows = [{"a": f"{bundle_name}::{a}", "b": f"{bundle_name}::{b}"} for a, b in edges]
        for i in range(0, len(rows), 2000):
            self._run("UNWIND $rows AS r MATCH (a:OKFConcept {key: r.a}), (b:OKFConcept {key: r.b}) "
                      "MERGE (a)-[:OKF_LINKS_TO]->(b)", rows=rows[i:i + 2000])

    def _write_describes(self, bundle_name: str, concepts: List[Concept]) -> int:
        """Bridge to the engineering graph when `resource` is a GitHub blob URL of an indexed repo."""
        from knowledge.graph.extractor import file_node_id

        rows = []
        for c in concepts:
            m = _GITHUB_BLOB_RX.match(str(c.doc.frontmatter.get("resource") or ""))
            if m:
                rows.append({"k": f"{bundle_name}::{c.id}", "f": file_node_id(m.group(1), m.group(3))})
        if not rows:
            return 0
        res = self._run("UNWIND $rows AS r MATCH (c:OKFConcept {key: r.k}) MATCH (f:Entity {node_id: r.f}) "
                        "MERGE (c)-[:OKF_DESCRIBES]->(f) RETURN count(*) AS n", rows=rows)
        return int(res[0]["n"]) if res else 0

    def neighbourhood(self, bundle_name: str, concept_id: str, hops: int = 1) -> Dict[str, Any]:
        hops = max(1, min(int(hops), 3))
        rows = self._run(
            f"MATCH (c:OKFConcept {{key: $k}}) OPTIONAL MATCH p=(c)-[:OKF_LINKS_TO*1..{hops}]-(n:OKFConcept) "
            "WITH c, collect(p) AS ps UNWIND (CASE WHEN size(ps)=0 THEN [null] ELSE ps END) AS p "
            "WITH c, p UNWIND (CASE WHEN p IS NULL THEN [null] ELSE relationships(p) END) AS r "
            "RETURN c.concept_id AS center, collect(DISTINCT CASE WHEN r IS NULL THEN null ELSE "
            "[startNode(r).concept_id, endNode(r).concept_id] END) AS edges",
            k=f"{bundle_name}::{concept_id}")
        if not rows:
            return {"center": concept_id, "nodes": [], "edges": []}
        edges = [e for e in rows[0]["edges"] if e]
        nodes = sorted({concept_id} | {x for e in edges for x in e})
        return {"center": concept_id, "nodes": nodes, "edges": edges}

    def count(self, bundle_name: Optional[str] = None) -> Dict[str, int]:
        where = "WHERE c.bundle = $b" if bundle_name else ""
        n = self._run(f"MATCH (c:OKFConcept) {where} RETURN count(c) AS n", b=bundle_name)[0]["n"]
        e = self._run(f"MATCH (c:OKFConcept)-[r:OKF_LINKS_TO]->() {where} RETURN count(r) AS n", b=bundle_name)[0]["n"]
        d = self._run(f"MATCH (c:OKFConcept)-[r:OKF_DESCRIBES]->() {where} RETURN count(r) AS n", b=bundle_name)[0]["n"]
        return {"concepts": int(n), "links": int(e), "describes": int(d)}
