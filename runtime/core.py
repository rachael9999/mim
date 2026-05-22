import os
import json
import uuid
from runtime.actor import MemoryActor, IndexActor
from runtime.visibility import DeleteCertIndex, DummyScopeGraph, VisibilityResolver
from runtime.snapshot_store import SnapshotStore
from runtime.index_snapshot import IndexSnapshotStore
from runtime.runtime import MimRuntime
from runtime.embeddings import OllamaEmbeddingProvider
from runtime.llm_extractor import GemmaExtractor

# 自动定位项目根目录下的 snapshots 文件夹
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", os.path.join(BASE_DIR, "snapshots"))

if not os.path.exists(SNAPSHOT_DIR):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

NODE_ID_FILE = os.path.join(SNAPSHOT_DIR, "node_id")

def get_node_id():
    if not os.path.exists(SNAPSHOT_DIR):
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    if os.path.exists(NODE_ID_FILE):
        with open(NODE_ID_FILE, "r") as f:
            return f.read().strip()
    new_id = str(uuid.uuid4())[:8]
    with open(NODE_ID_FILE, "w") as f:
        f.write(new_id)
    return new_id

NODE_ID = get_node_id()
PEERS_FILE = os.path.join(SNAPSHOT_DIR, "peers.json")

def get_peers():
    if os.path.exists(PEERS_FILE):
        with open(PEERS_FILE, "r") as f:
            return json.load(f)
    return []

def add_peer(url):
    peers = get_peers()
    if url not in peers:
        peers.append(url)
        with open(PEERS_FILE, "w") as f:
            json.dump(peers, f)
    return peers
# ... (existing imports)

# 替换提取器为更强大的 Gemma 模型
# 注意：这里使用用户本地已有的 gemma2:2b (对应您列表里的 gemma2:2b，虽然列表里写的是 gemma4:e2b 可能是别名，我先用标准名)
# 修正：使用用户本地的确切模型名称 gemma4:e2b
llm_extractor = GemmaExtractor(model="gemma4:e2b")
CERT_FILE = os.path.join(SNAPSHOT_DIR, "certs.json")

mems = {}        # id -> MemoryActor
index = IndexActor()
cert_index = DeleteCertIndex()
scope_graph = DummyScopeGraph()
store = SnapshotStore(SNAPSHOT_DIR)
index_store = IndexSnapshotStore(os.path.join(SNAPSHOT_DIR, "index.json"))
embed_provider = OllamaEmbeddingProvider(model="nomic-embed-text")
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

                    if "importance" in data:
                        imp_data = data["importance"]
                        mem.importance.set(imp_data["value"], imp_data.get("clock", 0), imp_data.get("node_id", "local"))

                    if "last_accessed" in data:
                        acc_data = data["last_accessed"]
                        mem.last_accessed.set(acc_data["value"], acc_data.get("clock", 0), acc_data.get("node_id", "local"))

                    if "links" in data:
                        mem.links.from_dict(data["links"])

                    runtime.recover_actor(mem)
                    mems[mid] = mem
                    index.add_memory(mem) # 确保索引被填充

    index_store.load(index)

def save_certs():
    with open(CERT_FILE, "w", encoding="utf-8") as f:
        json.dump(cert_index.to_dict(), f, ensure_ascii=False, indent=2)
