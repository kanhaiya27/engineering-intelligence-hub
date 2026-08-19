"""
Tests for ASTGraphExtractor in knowledge/graph/extractor.py
"""

import pytest

from knowledge.graph.base import NodeLabel, RelationshipType
from knowledge.graph.extractor import ASTGraphExtractor
from knowledge.schemas.artifacts import ArtifactType, SourceFile


@pytest.fixture
def sample_source_file():
    code = """
import os
from flask import Flask

class AppFactory:
    def create_app(self, config=None):
        app = Flask(__name__)
        return app

def helper_init():
    factory = AppFactory()
    return factory.create_app()
"""
    return SourceFile(
        artifact_id="flask:factory:src/factory.py",
        artifact_type=ArtifactType.SOURCE_CODE,
        repository="pallets/flask",
        commit_sha="4aa68d5",
        source_path="src/factory.py",
        raw_content=code,
        language="python",
        line_count=12,
    )


def test_ast_graph_extractor(sample_source_file):
    extractor = ASTGraphExtractor()
    nodes, edges = extractor.extract(sample_source_file)

    labels = {n.label for n in nodes}
    assert NodeLabel.FILE in labels
    assert NodeLabel.MODULE in labels
    assert NodeLabel.CLASS in labels
    assert NodeLabel.METHOD in labels
    assert NodeLabel.FUNCTION in labels

    # Check node provenance
    class_node = next(n for n in nodes if n.label == NodeLabel.CLASS)
    assert class_node.properties["repository"] == "pallets/flask"
    assert class_node.properties["commit_sha"] == "4aa68d5"
    assert class_node.properties["symbol_name"] == "AppFactory"
    assert class_node.properties["start_line"] > 0

    # Check relationships
    rel_types = {e.relationship for e in edges}
    assert RelationshipType.CONTAINS in rel_types
    assert RelationshipType.IMPORTS in rel_types
    assert RelationshipType.DEPENDS_ON in rel_types
