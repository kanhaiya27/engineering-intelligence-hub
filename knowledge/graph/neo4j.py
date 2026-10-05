"""
Engineering Intelligence Hub — Neo4j Graph Store
=================================================
Production-grade Neo4j graph store implementing BaseGraphStore.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

try:
    import neo4j
    from neo4j import GraphDatabase
    _NEO4J_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NEO4J_AVAILABLE = False

from core.exceptions import GraphStoreConnectionError
from core.logging import get_logger
from knowledge.graph.base import BaseGraphStore, GraphEdge, GraphNode

logger = get_logger(__name__)


class Neo4jGraphStore(BaseGraphStore):
    """
    Neo4j database implementation of BaseGraphStore.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: str = "neo4j",
    ) -> None:
        # Defaults come from settings (which read .env); this used to read only OS
        # environment variables, so a default-constructed store could not log in.
        from core.config import settings

        gs = settings.graph_store
        self.uri = uri or gs.uri
        self.username = username or gs.username
        self.password = password or gs.password or "changeme"
        self.database = database
        self._driver: Optional[neo4j.Driver] = None

    @property
    def store_name(self) -> str:
        return "neo4j_graph"

    def is_available(self) -> bool:
        """Check if Neo4j driver is installed and server is reachable."""
        if not _NEO4J_AVAILABLE:
            return False
        try:
            self.connect()
            with self._driver.session(database=self.database) as session:
                result = session.run("RETURN 1 AS ping")
                return result.single()["ping"] == 1
        except Exception:
            return False

    def connect(self) -> None:
        if not _NEO4J_AVAILABLE:
            raise GraphStoreConnectionError(
                "neo4j Python package is not installed.",
                details="Install via: pip install neo4j",
            )

        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.username, self.password),
                )
                self._init_constraints()
                logger.info(f"Connected to Neo4j at {self.uri}")
            except Exception as e:
                raise GraphStoreConnectionError(
                    f"Failed to connect to Neo4j at {self.uri}: {e}",
                    details=str(e),
                )

    def _init_constraints(self) -> None:
        """Ensure uniqueness constraints and indexes exist."""
        if not self._driver:
            return
        try:
            with self._driver.session(database=self.database) as session:
                # Generalized node_id index for fast lookups
                session.run(
                    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.node_id IS UNIQUE"
                )
        except Exception as e:
            logger.debug(f"Neo4j constraint creation skipped or already exists: {e}")

    def disconnect(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Disconnected from Neo4j.")

    def upsert_node(self, node: GraphNode) -> str:
        if not self._driver:
            self.connect()

        # Sanitize label (alphanumeric/underscore only)
        label = "".join(c for c in node.label if c.isalnum() or c == "_") or "Entity"

        cypher = f"""
        MERGE (n:{label} {{node_id: $node_id}})
        ON CREATE SET n += $properties, n:Entity
        ON MATCH SET n += $properties, n:Entity
        RETURN n.node_id AS id
        """
        params = {
            "node_id": node.node_id,
            "properties": node.properties,
        }

        with self._driver.session(database=self.database) as session:
            result = session.run(cypher, params)
            record = result.single()
            return record["id"] if record else node.node_id

    def upsert_edge(self, edge: GraphEdge) -> None:
        if not self._driver:
            self.connect()

        rel_type = "".join(c for c in edge.relationship if c.isalnum() or c == "_") or "RELATED"

        cypher = f"""
        MATCH (a:Entity {{node_id: $src}})
        MATCH (b:Entity {{node_id: $tgt}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $properties
        """
        params = {
            "src": edge.source_id,
            "tgt": edge.target_id,
            "properties": edge.properties,
        }

        with self._driver.session(database=self.database) as session:
            session.run(cypher, params)

    def get_node(self, node_id: str, label: Optional[str] = None) -> Optional[GraphNode]:
        if not self._driver:
            self.connect()

        lbl_clause = f":{label}" if label else ""
        cypher = f"""
        MATCH (n{lbl_clause} {{node_id: $node_id}})
        RETURN n.node_id AS node_id, labels(n) AS labels, properties(n) AS properties
        """
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher, {"node_id": node_id})
            record = result.single()
            if not record:
                return None

            labels = [lbl for lbl in record["labels"] if lbl != "Entity"]
            primary_label = labels[0] if labels else (label or "Entity")
            props = dict(record["properties"])
            return GraphNode(node_id=record["node_id"], label=primary_label, properties=props)

    def get_neighbours(
        self,
        node_id: str,
        relationship: Optional[str] = None,
        direction: str = "outbound",
        max_depth: int = 1,
    ) -> List[Tuple[GraphEdge, GraphNode]]:
        if not self._driver:
            self.connect()

        rel_pattern = f":{relationship}" if relationship else ""
        if direction == "outbound":
            pattern = f"-[r{rel_pattern}*1..{max_depth}]->(m:Entity)"
        elif direction == "inbound":
            pattern = f"<-[r{rel_pattern}*1..{max_depth}]-(m:Entity)"
        else:
            pattern = f"-[r{rel_pattern}*1..{max_depth}]-(m:Entity)"

        cypher = f"""
        MATCH (n:Entity {{node_id: $node_id}}){pattern}
        RETURN type(last(r)) AS rel_type, properties(last(r)) AS rel_props,
               startNode(last(r)).node_id AS src_id, endNode(last(r)).node_id AS tgt_id,
               m.node_id AS neighbor_id, labels(m) AS neighbor_labels, properties(m) AS neighbor_props
        """

        results: List[Tuple[GraphEdge, GraphNode]] = []
        with self._driver.session(database=self.database) as session:
            records = session.run(cypher, {"node_id": node_id})
            for rec in records:
                edge = GraphEdge(
                    source_id=rec["src_id"],
                    target_id=rec["tgt_id"],
                    relationship=rec["rel_type"],
                    properties=dict(rec["rel_props"]),
                )
                labels = [lbl for lbl in rec["neighbor_labels"] if lbl != "Entity"]
                primary_label = labels[0] if labels else "Entity"
                node = GraphNode(
                    node_id=rec["neighbor_id"],
                    label=primary_label,
                    properties=dict(rec["neighbor_props"]),
                )
                results.append((edge, node))

        return results

    def query(self, query_string: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        if not self._driver:
            self.connect()

        with self._driver.session(database=self.database) as session:
            result = session.run(query_string, parameters or {})
            return [dict(record) for record in result]

    def delete_node(self, node_id: str) -> bool:
        if not self._driver:
            self.connect()

        cypher = """
        MATCH (n:Entity {node_id: $node_id})
        DETACH DELETE n
        RETURN count(n) AS deleted
        """
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher, {"node_id": node_id})
            record = result.single()
            return bool(record and record["deleted"] > 0)

    def count_nodes(self, label: Optional[str] = None) -> int:
        if not self._driver:
            self.connect()

        lbl = f":{label}" if label else ":Entity"
        cypher = f"MATCH (n{lbl}) RETURN count(n) AS cnt"
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher)
            record = result.single()
            return record["cnt"] if record else 0

    def count_edges(self, relationship: Optional[str] = None) -> int:
        if not self._driver:
            self.connect()

        rel = f":{relationship}" if relationship else ""
        cypher = f"MATCH ()-[r{rel}]->() RETURN count(r) AS cnt"
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher)
            record = result.single()
            return record["cnt"] if record else 0

    # ------------------------------------------------------------------
    # Batch writes, hub-free expansion, co-change (fast Cypher versions)
    # ------------------------------------------------------------------
    _BATCH = 2000

    @staticmethod
    def _safe(name: str) -> str:
        return "".join(c for c in name if c.isalnum() or c == "_") or "Entity"

    def upsert_nodes(self, nodes: List[GraphNode]) -> None:
        if not self._driver:
            self.connect()
        by_label: Dict[str, List[Dict[str, Any]]] = {}
        for n in nodes:
            by_label.setdefault(self._safe(n.label), []).append({"id": n.node_id, "props": n.properties})
        with self._driver.session(database=self.database) as session:
            for label, rows in by_label.items():
                for i in range(0, len(rows), self._BATCH):
                    session.run(
                        f"UNWIND $rows AS row MERGE (n:Entity {{node_id: row.id}}) "
                        f"SET n:{label}, n += row.props",
                        {"rows": rows[i: i + self._BATCH]},
                    )

    def upsert_edges(self, edges: List[GraphEdge]) -> None:
        if not self._driver:
            self.connect()
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for e in edges:
            by_type.setdefault(self._safe(e.relationship), []).append(
                {"src": e.source_id, "tgt": e.target_id, "props": e.properties})
        with self._driver.session(database=self.database) as session:
            for rel, rows in by_type.items():
                for i in range(0, len(rows), self._BATCH):
                    session.run(
                        f"UNWIND $rows AS row MATCH (a:Entity {{node_id: row.src}}) "
                        f"MATCH (b:Entity {{node_id: row.tgt}}) MERGE (a)-[r:{rel}]->(b) SET r += row.props",
                        {"rows": rows[i: i + self._BATCH]},
                    )

    def expand(self, node_id: str, max_depth: int = 2, limit: int = 50,
               hub_labels: Tuple[str, ...] = ("Repository", "Commit")) -> List[Dict[str, Any]]:
        if not self._driver:
            self.connect()
        depth = max(1, int(max_depth))
        hubs = " OR ".join(f"x:{self._safe(h)}" for h in hub_labels) or "false"
        cypher = f"""
        MATCH p = (s:Entity {{node_id: $node_id}})-[*1..{depth}]-(m:Entity)
        WHERE m <> s AND none(x IN nodes(p)[1..] WHERE {hubs})
        WITH m, p ORDER BY length(p)
        WITH m, collect(p) AS ps
        WITH m, ps, length(ps[0]) AS hop
        WITH m, hop, [x IN ps WHERE length(x) = hop][..5] AS shortest
        RETURN m.node_id AS id, labels(m) AS labels, properties(m) AS props, hop,
               [x IN shortest | [r IN relationships(x) | [type(r), startNode(r).node_id, endNode(r).node_id]]] AS paths
        ORDER BY hop, id LIMIT $limit
        """
        out: List[Dict[str, Any]] = []
        with self._driver.session(database=self.database) as session:
            for rec in session.run(cypher, {"node_id": node_id, "limit": int(limit)}):
                labels = [lbl for lbl in rec["labels"] if lbl != "Entity"]
                node = GraphNode(rec["id"], labels[0] if labels else "Entity", dict(rec["props"]))
                paths = [[tuple(r) for r in p] for p in rec["paths"]]
                out.append({"node": node, "hop": rec["hop"], "paths": paths, "path": paths[0]})
        return out

    def co_changed(self, file_node_id: str, limit: int = 5, min_shared: int = 2) -> List[Tuple[GraphNode, int]]:
        if not self._driver:
            self.connect()
        cypher = """
        MATCH (f:Entity {node_id: $node_id})<-[:MODIFIES]-(c:Commit)-[:MODIFIES]->(o:File)
        WHERE o <> f
        WITH f, o, count(DISTINCT c) AS n WHERE n >= $min_shared
        MATCH (f)<-[:MODIFIES]-(cf:Commit) WITH f, o, n, count(DISTINCT cf) AS nf
        MATCH (o)<-[:MODIFIES]-(co:Commit) WITH o, n, nf, count(DISTINCT co) AS no
        RETURN o.node_id AS id, labels(o) AS labels, properties(o) AS props, n,
               toFloat(n) / sqrt(toFloat(nf * no)) AS score
        ORDER BY score DESC, n DESC, id LIMIT $limit
        """
        out: List[Tuple[GraphNode, int]] = []
        with self._driver.session(database=self.database) as session:
            for rec in session.run(cypher, {"node_id": file_node_id, "limit": int(limit),
                                            "min_shared": int(min_shared)}):
                labels = [lbl for lbl in rec["labels"] if lbl != "Entity"]
                out.append((GraphNode(rec["id"], labels[0] if labels else "Entity", dict(rec["props"])), rec["n"]))
        return out

    def clear(self) -> None:
        if not self._driver:
            self.connect()
        with self._driver.session(database=self.database) as session:
            while True:
                deleted = session.run(
                    "MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(n) AS c").single()["c"]
                if not deleted:
                    break

