from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import threading
import time

START_TIME = time.time()

from runtime.core import mems, index, cert_index, scope_graph, store, index_store, embed_provider, runtime, restore_all, save_certs, NODE_ID
from runtime.actor import MemoryActor
from runtime.visibility import VisibilityResolver
from runtime.extractor import DialogueMessage, MockExtractor

app = FastAPI(title="MIM HTTP API", version="0.1.0")
mim_lock = threading.Lock()

# --- Metrics Store (Production Hardening) ---
METRICS = {
    "requests_total": 0,
    "conflicts_detected": 0,
    "certs_hit": 0,
    "gc_runs": 0,
    "resync_required": 0
}

# --- Custom Exception Handling ---

class MIMException(Exception):
    def __init__(self, status_code: int, detail: str, code: str):
        self.status_code = status_code
        self.detail = detail
        self.code = code

@app.exception_handler(MIMException)
async def mim_exception_handler(request: Request, exc: MIMException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    METRICS["requests_total"] += 1
    response = await call_next(request)
    return response

# --- Schemas ---
# ... (existing schemas)

class RememberRequest(BaseModel):
    user_id: str
    content: str
    memory_type: str = "project"
    tag: str = "mim"

class RecallRequest(BaseModel):
    user_id: str
    tag: Optional[str] = None

class SearchRequest(BaseModel):
    user_id: str
    query: str

class ForgetRequest(BaseModel):
    memory_id: str

class IngestRequest(BaseModel):
    user_id: str
    text: str

class PullRequest(BaseModel):
    user_id: str
    vector: Dict[str, int] # 客户端当前的版本向量

class SyncRequest(BaseModel):
    source_path: str

class MemoryItem(BaseModel):
    id: str
    owner_id: str
    content: str
    memory_type: str
    clock: int

# --- API Endpoints ---

@app.post("/v1/pull")
def api_pull(req: PullRequest):
    """增量拉取接口：根据客户端向量返回增量 Actor 状态"""
    with mim_lock:
        from runtime.clocks import VersionVector
        client_vv = VersionVector(req.vector)

        updates = []
        vis = VisibilityResolver(cert_index, scope_graph)

        # 找出那些在客户端向量之后更新过的 Actor
        for mid, actor in mems.items():
            if actor.owner_id != req.user_id:
                continue

            if not vis.object_visible(actor):
                continue

            # 对比版本向量
            actor_vv = VersionVector(actor._meta.get("version_vector", {}))
            if not client_vv.dominates(actor_vv):
                # 客户端没有包含该 Actor 的最新状态
                updates.append(actor.to_dict())

        return {
            "node_id": NODE_ID,
            "current_vector": {NODE_ID: int(time.time())}, # 简单起见返回节点时间戳
            "updates": updates,
            "certs": cert_index.to_dict() # 同时同步证书
        }

@app.post("/v1/sync_single")
def api_sync_single(remote_data: Dict[str, Any]):
    """接收单个 Actor 的主动推送"""
    with mim_lock:
        mid = remote_data["id"]
        if mid in mems:
            mems[mid].merge_state(remote_data, cert_index)
        else:
            mems[mid] = MemoryActor(id=mid, owner_id=remote_data["owner_id"], content="", memory_type=remote_data["memory_type"]["value"], tags=[])
            mems[mid].merge_state(remote_data, cert_index)

        store.save(mems[mid])
        index.add_memory(mems[mid])
        return {"status": "merged", "id": mid}

@app.post("/v1/peers")
def api_add_peer(req: Dict[str, str]):
    """注册 Peer 节点"""
    url = req.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Missing url")
    from runtime.core import add_peer
    peers = add_peer(url)
    return {"peers": peers}

@app.on_event("startup")
def startup_event():
    with mim_lock:
        restore_all()

@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": time.time()}

@app.post("/v1/remember")
def api_remember(req: RememberRequest):
    with mim_lock:
        try:
            mem_id = f"mem_{int(time.time()*1000)}"
            mem = MemoryActor(id=mem_id, owner_id=req.user_id, content="", memory_type=req.memory_type, tags=[])
            mems[mem_id] = mem
            runtime.dispatch(mem, "update_content", {"content": req.content})
            runtime.dispatch(mem, "add_tag", {"tag": req.tag})
            index_store.save(index)
            return {"id": mem_id, "status": "created"}
        except Exception as e:
            raise MIMException(status_code=500, detail=str(e), code="INTERNAL_ERROR")

@app.post("/v1/recall", response_model=List[MemoryItem])
def api_recall(req: RecallRequest):
    with mim_lock:
        vis = VisibilityResolver(cert_index, scope_graph)
        ids = index.query(owner=req.user_id, tag=req.tag)
        results = []
        for mid in ids:
            mem = mems.get(mid)
            if not mem:
                continue

            # Visibility Check
            if not vis.object_visible(mem):
                METRICS["certs_hit"] += 1
                continue

            results.append(MemoryItem(
                id=mem.id,
                owner_id=mem.owner_id,
                content=mem.content.value,
                memory_type=mem.memory_type.value,
                clock=mem._meta.get("clock", 0)
            ))
        return results

@app.post("/v1/search")
def api_search(req: SearchRequest):
    with mim_lock:
        raw_results = index.hybrid_query(owner=req.user_id, query_text=req.query, provider=embed_provider)
        vis = VisibilityResolver(cert_index, scope_graph)
        results = []
        for mid, score in raw_results:
            mem = mems.get(mid)
            if mem:
                if not vis.object_visible(mem):
                    METRICS["certs_hit"] += 1
                    continue

                results.append({
                    "id": mid,
                    "content": mem.content.value,
                    "score": score,
                    "type": mem.memory_type.value
                })
        return results

@app.post("/v1/forget")
def api_forget(req: ForgetRequest):
    with mim_lock:
        mem = mems.get(req.memory_id)
        vis = VisibilityResolver(cert_index, scope_graph)

        if mem and not vis.object_visible(mem):
            METRICS["conflicts_detected"] += 1
            raise MIMException(status_code=410, detail="Memory already gone by certificate", code="ALREADY_FORGOTTEN")

        if not mem:
            raise MIMException(status_code=404, detail="Memory not found", code="NOT_FOUND")

        cert = {"scope": req.memory_id, "delete_clock": {"local": 1}, "policy": "delete_wins", "timestamp": time.time()}
        runtime.dispatch(mem, "delete", {"certificate": cert})
        cert_index.add(cert)
        save_certs()
        return {"status": "forgotten", "id": req.memory_id}

@app.post("/v1/ingest")
def api_ingest(req: IngestRequest):
    with mim_lock:
        try:
            from runtime.core import llm_extractor
            messages = [DialogueMessage(role="user", content=req.text)]
            extracted = runtime.ingest_dialogue(req.user_id, messages, llm_extractor)
            for mem in extracted:
                mems[mem.id] = mem
            index_store.save(index)
            return {"extracted_count": len(extracted)}
        except Exception as e:
            raise MIMException(status_code=500, detail=str(e), code="INGEST_ERROR")

@app.get("/metrics")
def get_metrics():
    with mim_lock:
        return {
            **METRICS,
            "mems_loaded": len(mems),
            "certs_loaded": len(cert_index.by_scope),
            "uptime": time.time() - START_TIME
        }

@app.post("/v1/sync")
def api_sync(req: SyncRequest):
    with mim_lock:
        try:
            METRICS["resync_required"] += 1
            # 复用 cli.py 中的逻辑 (此处为了简单直接内联，生产应放在 core.py)
            import os
            source_node_dir = req.source_path
            remote_cert_file = os.path.join(source_node_dir, "certs.json")
            if os.path.exists(remote_cert_file):
                import json
                with open(remote_cert_file, "r", encoding="utf-8") as f:
                    remote_certs = json.load(f)
                    for scope, cert in remote_certs.items():
                        cert_index.add(cert)
                save_certs()

            if os.path.exists(source_node_dir):
                for fn in os.listdir(source_node_dir):
                    if fn.endswith(".json") and not (fn.startswith("index") or fn == "certs.json"):
                        mid = fn[:-5]
                        remote_path = os.path.join(source_node_dir, fn)
                        import json
                        with open(remote_path, "r", encoding="utf-8") as f:
                            remote_data = json.load(f)

                        # Epoch Gate Check (Integration Point)
                        if "clock" in remote_data.get("_meta", {}):
                            if not runtime.epoch_gate.is_allowed(remote_data["_meta"]["clock"]):
                                METRICS["conflicts_detected"] += 1
                                continue

                        if mid in mems:
                            mems[mid].merge_state(remote_data, cert_index)
                        else:
                            mems[mid] = MemoryActor(id=remote_data["id"], owner_id=remote_data["owner_id"], content="", memory_type=remote_data["memory_type"]["value"], tags=[])
                            mems[mid].merge_state(remote_data, cert_index)
                        store.save(mems[mid])
                        index.add_memory(mems[mid])
            index_store.save(index)
            return {"status": "sync_completed"}
        except Exception as e:
            raise MIMException(status_code=500, detail=str(e), code="SYNC_ERROR")
