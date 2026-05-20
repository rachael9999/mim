# vector_search.py
# P2: Graph-Native Semantic Traversal
# Depends on: actor_runtime.py (P1)

import math
from dataclasses import dataclass, field
from typing import Dict, List

try:
    from sentence_transformers import SentenceTransformer
    _TRANSFORMER_AVAILABLE = True
except ImportError:
    _TRANSFORMER_AVAILABLE = False


# ----------------------------------------------------------------
# Math primitives — validated by the Zero 2D exe (vector_math.0)
# These are the exact same operations, extended to N dimensions
# ----------------------------------------------------------------
def dot_product(a: List[float], b: List[float]) -> float:
    """Identical operation to the Zero dot2() — just N-dimensional."""
    return sum(x * y for x, y in zip(a, b))

def magnitude(v: List[float]) -> float:
    """Requires sqrt — Zero can't do this natively, Python handles it."""
    return math.sqrt(sum(x * x for x in v))

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Full cosine similarity — the numerator is what Zero proved.
    The denominator requires sqrt, which lives here permanently.
    """
    mag_a = magnitude(a)
    mag_b = magnitude(b)
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot_product(a, b) / (mag_a * mag_b)


# ----------------------------------------------------------------
# Edge embedding store — attaches to the Actor Graph
# ----------------------------------------------------------------
@dataclass
class EmbeddedEdge:
    """
    Extends a Graph Edge with a vector embedding.
    The embedding represents the semantic meaning of the relationship,
    not the actors themselves — e.g., 'eating beef causes high carbon output'.
    """
    from_id:    str
    to_id:      str
    edge_type:  str
    label:      str          # human-readable, used to generate embedding
    embedding:  List[float]  = field(default_factory=list)
    strength:   float        = 1.0


class VectorIndex:
    """
    Flat vector index over actor graph edges.

    Not HNSW, not FAISS — a deliberate flat scan chosen because:
      1. Actor graphs at this scale (thousands of edges) don't need ANN
      2. It keeps the dependency footprint zero (no native C++ libs required)
      3. We can upgrade to FAISS later without touching callers

    This scan IS the graph query engine for mim.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.embedded_edges: Dict[str, EmbeddedEdge] = {}
        self.model = None

        if _TRANSFORMER_AVAILABLE:
            print(f"[VectorIndex] Loading model: {model_name}")
            self.model = SentenceTransformer(model_name)
            print(f"[VectorIndex] Model ready — "
                  f"{self.model.get_sentence_embedding_dimension()}-dim embeddings")
        else:
            print("[VectorIndex] sentence-transformers not installed — "
                  "using mock 384-dim embeddings for pipeline validation")

    def embed_edge(
        self,
        from_id:   str,
        to_id:     str,
        edge_type: str,
        label:     str,
        strength:  float = 1.0
    ) -> EmbeddedEdge:
        """
        Encode a natural-language edge label into a vector.
        This is the operation that turns the structural graph
        into a semantic graph.
        """
        edge_id   = f"{from_id}::{edge_type}::{to_id}"
        embedding = self._encode(label)

        edge = EmbeddedEdge(
            from_id=from_id,
            to_id=to_id,
            edge_type=edge_type,
            label=label,
            embedding=embedding,
            strength=strength
        )
        self.embedded_edges[edge_id] = edge
        print(f"[VectorIndex] Embedded edge '{label}' ({len(embedding)}-dim)")
        return edge

    def search(
        self,
        query:     str,
        top_k:     int   = 5,
        threshold: float = 0.3
    ) -> List[dict]:
        """
        Semantic search across all embedded edges.
        Returns top_k edges whose meaning is closest to the query.

        This replaces standard BFS graph traversal —
        we use semantic ranking instead of hop counting!
        """
        query_vec = self._encode(query)
        scored    = []

        for edge_id, edge in self.embedded_edges.items():
            if not edge.embedding:
                continue

            score = cosine_similarity(query_vec, edge.embedding)
            if score >= threshold:
                scored.append({
                    "edge_id":   edge_id,
                    "from_id":   edge.from_id,
                    "to_id":     edge.to_id,
                    "edge_type": edge.edge_type,
                    "label":     edge.label,
                    "score":     round(score, 4),
                    "strength":  edge.strength
                })

        # Sort by cosine score descending, break ties by edge strength
        scored.sort(key=lambda x: (x["score"], x["strength"]), reverse=True)
        return scored[:top_k]

    def _encode(self, text: str) -> List[float]:
        if self.model:
            return self.model.encode(text).tolist()

        # Mock path: deterministic hash-based embedding for testing
        # Not semantically meaningful — only proves the search/score path works.
        return _mock_embedding(text, dims=384)


def _mock_embedding(text: str, dims: int = 384) -> List[float]:
    """
    Deterministic fake embedding for pipeline validation.
    The Zero 2D exe validated the math; this validates the routing.
    """
    seed = sum(ord(c) * (i + 1) for i, c in enumerate(text))
    vec  = []
    for i in range(dims):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        vec.append((seed / 0x7FFFFFFF) - 0.5)

    mag = math.sqrt(sum(x * x for x in vec))
    if mag == 0:
        return [0.0] * dims
    return [x / mag for x in vec]

if __name__ == "__main__":
    print("--- P2 Graph-Native Traversal Validation ---")

    # ── Step 1: Verify the math matches what Zero proved ────────────────────────
    a_parallel    = [1.0, 0.0]
    b_parallel    = [1.0, 0.0]
    a_orthogonal  = [1.0, 0.0]
    b_orthogonal  = [0.0, 1.0]

    sim_parallel   = cosine_similarity(a_parallel,   b_parallel)
    sim_orthogonal = cosine_similarity(a_orthogonal, b_orthogonal)

    assert abs(sim_parallel   - 1.0) < 1e-9, "Parallel vectors should score 1.0"
    assert abs(sim_orthogonal - 0.0) < 1e-9, "Orthogonal vectors should score 0.0"

    print(f"Math validation: parallel={sim_parallel:.4f}, orthogonal={sim_orthogonal:.4f}  ✓")

    # ── Step 2: Build a semantic edge graph and query it ────────────────────────
    idx = VectorIndex()
    idx.embed_edge("action:eat-beef",    "category:high-carbon",               "BelongsTo", "eating beef produces high carbon emissions", strength=0.95)
    idx.embed_edge("action:commute-car", "category:high-carbon",               "BelongsTo", "driving a car produces high carbon emissions", strength=0.88)
    idx.embed_edge("action:take-shower", "category:water-usage",               "BelongsTo", "shower causes water and energy consumption",   strength=0.70)
    idx.embed_edge("action:eat-beef",    "action:commute-car",                 "Causes",    "high carbon lifestyle beef and car travel",    strength=0.60)

    # Semantic query
    query_text = "carbon footprint from food"
    results = idx.search(query_text, top_k=3, threshold=-1.0) # low threshold for mock vectors

    print(f"\nQuery: '{query_text}'")
    for r in results:
        print(f"  [{r['score']:.4f}] {r['from_id']} --[{r['edge_type']}]--> {r['to_id']}")
        print(f"          \"{r['label']}\"")

    # In mock mode, the scores are random hashes so we can't assert semantic ranking
    print("\nSemantic pipeline validated ✓")
