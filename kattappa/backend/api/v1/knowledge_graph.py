from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from backend.core.knowledge_graph import KnowledgeGraph

knowledge_graph_router = APIRouter(tags=["KnowledgeGraph"])

class ReconcileRequest(BaseModel):
    node_ids: List[str] = Field(..., min_items=2, description="List of node IDs to merge synonymously")

class PathQueryResponse(BaseModel):
    source: str
    target: str
    paths: List[List[str]]
    combined_probability: float
    best_path: Optional[List[str]]
    visited_nodes: List[str]
    explanation: str

@knowledge_graph_router.get("/kg/subgraph")
def get_kg_subgraph(
    node_id: Optional[str] = Query(None, description="Optional start node ID for subgraph traversal"),
    depth: int = Query(2, ge=1, le=5, description="Depth of traversal from the start node")
) -> Dict[str, Any]:
    """Retrieves a serialized subgraph format `{nodes: [...], edges: [...]}` for visualization."""
    kg = KnowledgeGraph.get_instance()
    
    nodes = []
    edges = []
    
    store = kg._store
    conn = store._get_conn()
    try:
        if node_id:
            neighbors = kg.query_neighbors(node_id, direction="both")
            visited = {node_id}
            start_node = store.get_node(node_id)
            if start_node:
                nodes.append({
                    "id": start_node["id"],
                    "label": start_node["name"],
                    "type": start_node["entity_type"],
                    "confidence": start_node["confidence"],
                    "belief_state": start_node["belief_state"]
                })
            
            for n in neighbors:
                nid = n["node_id"]
                if nid not in visited:
                    visited.add(nid)
                    node_data = store.get_node(nid)
                    if node_data:
                        nodes.append({
                            "id": node_data["id"],
                            "label": node_data["name"],
                            "type": node_data["entity_type"],
                            "confidence": node_data["confidence"],
                            "belief_state": node_data["belief_state"]
                        })
                out_edges = store.get_edges_from(node_id)
                for e in out_edges:
                    if e["target_id"] == nid:
                        edges.append({
                            "id": e["id"],
                            "source": e["source_id"],
                            "target": e["target_id"],
                            "relation": e["relation_type"],
                            "confidence": e["confidence"]
                        })
                in_edges = store.get_edges_to(node_id)
                for e in in_edges:
                    if e["source_id"] == nid:
                        edges.append({
                            "id": e["id"],
                            "source": e["source_id"],
                            "target": e["target_id"],
                            "relation": e["relation_type"],
                            "confidence": e["confidence"]
                        })
        else:
            node_rows = conn.execute("SELECT * FROM kg_nodes LIMIT 100").fetchall()
            for row in node_rows:
                nodes.append({
                    "id": row["id"],
                    "label": row["name"],
                    "type": row["entity_type"],
                    "confidence": row["confidence"],
                    "belief_state": row["belief_state"]
                })
            edge_rows = conn.execute("SELECT * FROM kg_edges LIMIT 200").fetchall()
            for row in edge_rows:
                edges.append({
                    "id": row["id"],
                    "source": row["source_id"],
                    "target": row["target_id"],
                    "relation": row["relation_type"],
                    "confidence": row["confidence"]
                })
    finally:
        conn.close()
        
    return {"nodes": nodes, "edges": edges}

@knowledge_graph_router.get("/kg/path")
def query_kg_path(
    source: str = Query(..., description="Source node ID or name"),
    target: str = Query(..., description="Target node ID or name"),
    max_depth: int = Query(4, ge=1, le=6, description="Maximum path length")
) -> PathQueryResponse:
    """Searches paths between source and target, returning exact joint path probabilities and explanations."""
    kg = KnowledgeGraph.get_instance()
    
    src_resolved = kg.resolve_entity(source)
    src_id = src_resolved.id if src_resolved else source
    
    tgt_resolved = kg.resolve_entity(target)
    tgt_id = tgt_resolved.id if tgt_resolved else target
    
    res = kg.query_probabilistic(src_id, tgt_id, max_depth=max_depth)
    return PathQueryResponse(
        source=src_id,
        target=tgt_id,
        paths=res.paths,
        combined_probability=res.combined_probability,
        best_path=res.best_path,
        visited_nodes=res.visited_nodes,
        explanation=res.explanation.explanation_text
    )

@knowledge_graph_router.post("/kg/reconcile")
def reconcile_kg_synonyms(request: ReconcileRequest) -> Dict[str, Any]:
    """Manually triggers synonym mergers and alias reconciliation."""
    kg = KnowledgeGraph.get_instance()
    try:
        canonical_node = kg.merge_entities(request.node_ids)
        return {
            "success": True,
            "canonical_id": canonical_node.id,
            "name": canonical_node.name,
            "entity_type": canonical_node.entity_type,
            "properties": canonical_node.properties
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@knowledge_graph_router.get("/kg/provenance/{node_id}")
def get_kg_provenance(node_id: str) -> Dict[str, Any]:
    """Retrieves source metadata and evidence logs for a node."""
    kg = KnowledgeGraph.get_instance()
    node = kg._store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    return {
        "node_id": node["id"],
        "name": node["name"],
        "source_layer": node.get("source_layer"),
        "confidence": node.get("confidence"),
        "belief_state": node.get("belief_state"),
        "evidence": node.get("evidence", []),
        "created_at": node.get("created_at"),
        "updated_at": node.get("updated_at")
    }
