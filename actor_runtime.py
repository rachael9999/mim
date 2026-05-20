# actor_runtime.py
# P1: Python as the stateful CRDT host with Snapshot/Restore
# P3: Decentralized Spreading Activation (Query Federation)

import subprocess
import json
import uuid
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Set
import threading
import time
import os
from vector_search import cosine_similarity, _mock_embedding

# ── P1: Actor State ────────────────────────────────────────────────────────
@dataclass
class ActorState:
    """Python owns this. Zero computes transitions on it."""
    carbon_total: int = 0
    frequency:    int = 0
    name_hash:    int = 0
    name_ts:      int = 0
    last_snapshot: float = field(default_factory=time.time)

# ── P3: Query Envelope & Local Edges ───────────────────────────────────────
@dataclass
class QueryEnvelope:
    """
    Spreading Activation context passed between actors.
    visited prevents cycles, max_activations limits fan-out.
    """
    query_id:               str
    query_text:             str
    query_vec:              List[float]
    max_hops:               int
    visited:                Set[str]          = field(default_factory=set)
    origin_id:              str               = ""
    max_activations_per_hop: int              = 3
    threshold:              float             = 0.4


@dataclass
class LocalEdge:
    to_id:      str
    edge_type:  str
    label:      str
    embedding:  List[float]
    strength:   float = 1.0


# ── Actor Handle ───────────────────────────────────────────────────────────
class ActorHandle:
    def __init__(self, actor_id: str, registry: "ActorRegistry", exe_path: str, snapshot_dir: Path):
        self.actor_id     = actor_id
        self.registry     = registry
        self.exe_path     = exe_path
        self.snapshot_dir = snapshot_dir
        self.lock         = threading.Lock()

        # P1: Stateful CRDT
        self.state = self._load_snapshot() or ActorState()

        # P3: Local Decentralized Vector Index
        self.local_edges: Dict[str, LocalEdge] = {}

    def send(self, message: dict) -> dict:
        with self.lock:
            msg_type = message.get("type")

            if msg_type == "record_carbon":
                next_total = self.state.carbon_total + message["amount"]
                self.state.carbon_total = next_total
                self.state.frequency   += 1
                if self.state.frequency % 10 == 0:
                    self._persist_snapshot()
                return {"status": "ok", "total": self.state.carbon_total}

            elif msg_type == "set_name":
                local_ts = self.state.name_ts
                remote_ts = message["timestamp"]
                if remote_ts > local_ts:
                    self.state.name_hash = message["hash"]
                    self.state.name_ts = remote_ts
                elif local_ts == remote_ts:
                    self.state.name_hash = max(self.state.name_hash, message["hash"])
                return {"status": "ok", "name_hash": self.state.name_hash}

            elif msg_type == "get_total":
                return {
                    "total":     self.state.carbon_total,
                    "frequency": self.state.frequency,
                    "name_hash": self.state.name_hash
                }

            elif msg_type == "snapshot":
                return self._persist_snapshot()

            elif msg_type == "link":
                # P3: Add edge to LOCAL index only
                edge_id = f"{self.actor_id}::{message['edge_type']}::{message['to_id']}"
                label = message["label"]
                embedding = self.registry.encode(label)
                self.local_edges[edge_id] = LocalEdge(
                    to_id=message["to_id"],
                    edge_type=message["edge_type"],
                    label=label,
                    embedding=embedding,
                    strength=message.get("strength", 1.0)
                )
                print(f"[{self.actor_id}] +edge '{label}' -> {message['to_id']}")
                return {"status": "ok"}

            elif msg_type == "semantic_query":
                # P3: Spreading Activation Query
                envelope: QueryEnvelope = message["envelope"]
                results = self._handle_query(envelope)
                return {"status": "ok", "results": results}

            return {"status": "unknown"}

    def _handle_query(self, envelope: QueryEnvelope) -> List[dict]:
        # 1. Cycle Detection
        if self.actor_id in envelope.visited:
            return []
        envelope.visited.add(self.actor_id)

        # 2. Local Scoring against local_edges only
        local_results = []
        scored_neighbors: List[Tuple[float, str]] = []

        for edge_id, edge in self.local_edges.items():
            if not edge.embedding: continue

            score = cosine_similarity(envelope.query_vec, edge.embedding)
            local_results.append({
                "edge_id":   edge_id,
                "from_id":   self.actor_id,
                "to_id":     edge.to_id,
                "edge_type": edge.edge_type,
                "label":     edge.label,
                "score":     round(score, 4),
                "strength":  edge.strength,
                "hop":       envelope.max_hops
            })
            if score >= envelope.threshold:
                scored_neighbors.append((score, edge.to_id))

        # 3. Directed Forwarding
        forwarded_results = []
        if envelope.max_hops > 0 and scored_neighbors:
            scored_neighbors.sort(reverse=True)
            to_forward = scored_neighbors[:envelope.max_activations_per_hop]

            for score, neighbor_id in to_forward:
                neighbor = self.registry.get_actor(neighbor_id)
                if neighbor is None:
                    continue # Network hook for distributed setup

                # Prevent silent pruning across parallel branches by passing a copy
                child_envelope = QueryEnvelope(
                    query_id=envelope.query_id,
                    query_text=envelope.query_text,
                    query_vec=envelope.query_vec,
                    max_hops=envelope.max_hops - 1,
                    visited=set(envelope.visited), # Independent copy for this branch
                    origin_id=envelope.origin_id,
                    max_activations_per_hop=envelope.max_activations_per_hop,
                    threshold=envelope.threshold
                )

                print(f"[Spreading] {self.actor_id} --({score:.2f})--> {neighbor_id}")
                neighbor_res = neighbor.send({"type": "semantic_query", "envelope": child_envelope})
                if neighbor_res and "results" in neighbor_res:
                    forwarded_results.extend(neighbor_res["results"])

        # 4. Aggregation and Deduplication
        all_results = local_results + forwarded_results
        seen = set()
        deduped = []
        for r in all_results:
            if r["edge_id"] not in seen:
                seen.add(r["edge_id"])
                deduped.append(r)

        return deduped

    def _persist_snapshot(self) -> dict:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = self.snapshot_dir / f"{self.actor_id.replace(':', '_')}.json"
        snapshot = asdict(self.state)
        snapshot_path.write_text(json.dumps(snapshot, indent=2))
        self.state.last_snapshot = time.time()
        return {"status": "snapshot_ok", "path": str(snapshot_path)}

    def _load_snapshot(self) -> Optional[ActorState]:
        snapshot_path = self.snapshot_dir / f"{self.actor_id.replace(':', '_')}.json"
        if snapshot_path.exists():
            data = json.loads(snapshot_path.read_text())
            return ActorState(**{k: v for k, v in data.items() if k in ActorState.__dataclass_fields__})
        return None


# ── Registry: Directory & Bootstrap ────────────────────────────────────────
class ActorRegistry:
    def __init__(self):
        base_path = Path(__file__).parent
        self.exe_path     = base_path / ".zero" / "out" / "action_actor.exe"
        self.snapshot_dir = base_path / ".zero" / "snapshots"

        self.actors:          Dict[str, ActorHandle] = {}
        self.bootstrap_vecs:  Dict[str, List[float]] = {}
        self._model = None # Mock by default

    def spawn(self, actor_id: str) -> ActorHandle:
        if actor_id not in self.actors:
            handle = ActorHandle(
                actor_id=actor_id,
                registry=self,
                exe_path=str(self.exe_path),
                snapshot_dir=self.snapshot_dir
            )
            self.actors[actor_id] = handle
            self.bootstrap_vecs[actor_id] = self.encode(actor_id)
            print(f"[Registry] spawned '{actor_id}'")
        return self.actors[actor_id]

    def get_actor(self, actor_id: str) -> Optional[ActorHandle]:
        return self.actors.get(actor_id)

    def encode(self, text: str) -> List[float]:
        return _mock_embedding(text, dims=384)

    def query(self, entry_actor_id: str, query_text: str,
              max_hops: int = 3, threshold: float = 0.4,
              max_activations_per_hop: int = 3) -> List[dict]:

        actor = self.get_actor(entry_actor_id)
        if not actor: raise KeyError(f"Entry actor '{entry_actor_id}' not found")

        envelope = QueryEnvelope(
            query_id=str(uuid.uuid4())[:8],
            query_text=query_text,
            query_vec=self.encode(query_text),
            max_hops=max_hops,
            max_activations_per_hop=max_activations_per_hop,
            threshold=threshold,
            origin_id=entry_actor_id
        )
        res = actor.send({"type": "semantic_query", "envelope": envelope})
        results = res.get("results", [])
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def bootstrap_query(self, query_text: str, top_k_entry: int = 2, **kwargs) -> List[dict]:
        query_vec = self.encode(query_text)
        scored = [
            (cosine_similarity(query_vec, vec), aid)
            for aid, vec in self.bootstrap_vecs.items()
        ]
        scored.sort(reverse=True)
        entry_points = [aid for _, aid in scored[:top_k_entry]]
        print(f"\n[Bootstrap] Entry points for '{query_text}': {entry_points}")

        all_results = []
        seen = set()
        for entry_id in entry_points:
            for r in self.query(entry_id, query_text, **kwargs):
                if r["edge_id"] not in seen:
                    seen.add(r["edge_id"])
                    all_results.append(r)

        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results
