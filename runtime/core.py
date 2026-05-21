import os
import json
from runtime.actor import MemoryActor, IndexActor
from runtime.visibility import DeleteCertIndex, DummyScopeGraph, VisibilityResolver
from runtime.snapshot_store import SnapshotStore
from runtime.index_snapshot import IndexSnapshotStore
from runtime.runtime import MimRuntime
from runtime.embeddings import MockEmbeddingProvider

SNAPSHOT_DIR = "mim/snapshots"
CERT_FILE = os.path.join(SNAPSHOT_DIR, "certs.json")

mems = {}        # id -> MemoryActor
index = IndexActor()
cert_index = DeleteCertIndex()
scope_graph = DummyScopeGraph()
store = SnapshotStore(SNAPSHOT_DIR)
index_store = IndexSnapshotStore(os.path.join(SNAPSHOT_DIR, "index.json"))
embed_provider = MockEmbeddingProvider()
runtime = MimRuntime(store, index, cert_index, SNAPSHOT_DIR, embedding_provider=embed_provider)

def restore_all():
    if os.path.exists(CERT_FILE):
        with open(CERT_FILE, "r", encoding="utf-8") as f:
            cert_index.from_dict(json.load(f))

    if os.path.exists(SNAPSHOT_DIR):
        for fn in os.listdir(SNAPSHOT_DIR):
            if fn.endswith(".json") and not (fn.startswith("index") or fn == "certs.json" or fn == "processed_messages.json"):
                mid = fn[:-5]
                data = store.load(mid)
                if data:
                    mem = MemoryActor(
                        id=data["id"],
                        owner_id=data["owner_id"],
                        content=data["content"]["value"],
                        memory_type=data["memory_type"]["value"],
                        tags=list(data["tags"]["adds"].keys()),
                        _meta=data.get("_meta"),
                        _deleted=data.get("_deleted", False),
                        delete_certificate=data.get("delete_certificate")
                    )
                    if "status" in data:
                        status_data = data["status"]
                        if isinstance(status_data, dict):
                            mem.status.set(status_data["value"],
                                           status_data.get("clock", 0),
                                           status_data.get("node_id", "local"))
                        else:
                            mem.status.set(status_data, 0, "local")

                    if "embedding" in data and data["embedding"]["value"]:
                        mem.embedding.set(data["embedding"]["value"],
                                          data["embedding"].get("clock", 0),
                                          data["embedding"].get("node_id", "local"))

                    runtime.recover_actor(mem)
                    mems[mid] = mem
                    index.add_memory(mem) # 确保索引被填充

    index_store.load(index)

def save_certs():
    with open(CERT_FILE, "w", encoding="utf-8") as f:
        json.dump(cert_index.to_dict(), f, ensure_ascii=False, indent=2)
