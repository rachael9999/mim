from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import threading
import time

from runtime.core import mems, index, cert_index, scope_graph, store, index_store, embed_provider, runtime, restore_all, save_certs
from runtime.actor import MemoryActor
from runtime.visibility import VisibilityResolver
from runtime.extractor import DialogueMessage, MockExtractor

app = FastAPI(title="MIM HTTP API", version="0.1.0")
mim_lock = threading.Lock()

# --- Schemas ---

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

class SyncRequest(BaseModel):
    source_path: str

class MemoryItem(BaseModel):
    id: str
    owner_id: str
    content: str
    memory_type: str
    clock: int

# --- API Endpoints ---

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
        mem_id = f"mem_{int(time.time()*1000)}"
        mem = MemoryActor(id=mem_id, owner_id=req.user_id, content="", memory_type=req.memory_type, tags=[])
        mems[mem_id] = mem
        runtime.dispatch(mem, "update_content", {"content": req.content})
        runtime.dispatch(mem, "add_tag", {"tag": req.tag})
        index_store.save(index)
        return {"id": mem_id, "status": "created"}

@app.post("/v1/recall", response_model=List[MemoryItem])
def api_recall(req: RecallRequest):
    with mim_lock:
        vis = VisibilityResolver(cert_index, scope_graph)
        ids = index.query(owner=req.user_id, tag=req.tag)
        results = []
        for mid in ids:
            mem = mems.get(mid)
            if mem and vis.object_visible(mem):
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
        results = []
        for mid, score in raw_results:
            mem = mems.get(mid)
            if mem:
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
        if not mem:
            raise HTTPException(status_code=404, detail="Memory not found")
        cert = {"scope": req.memory_id, "delete_clock": {"local": 1}, "policy": "delete_wins"}
        runtime.dispatch(mem, "delete", {"certificate": cert})
        cert_index.add(cert)
        save_certs()
        return {"status": "forgotten", "id": req.memory_id}

@app.post("/v1/ingest")
def api_ingest(req: IngestRequest):
    with mim_lock:
        extractor = MockExtractor()
        messages = [DialogueMessage(role="user", content=req.text)]
        extracted = runtime.ingest_dialogue(req.user_id, messages, extractor)
        for mem in extracted:
            mems[mem.id] = mem
        index_store.save(index)
        return {"extracted_count": len(extracted)}

@app.post("/v1/sync")
def api_sync(req: SyncRequest):
    with mim_lock:
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
                    if mid in mems:
                        mems[mid].merge_state(remote_data, cert_index)
                    else:
                        mems[mid] = MemoryActor(id=remote_data["id"], owner_id=remote_data["owner_id"], content="", memory_type=remote_data["memory_type"]["value"], tags=[])
                        mems[mid].merge_state(remote_data, cert_index)
                    store.save(mems[mid])
                    index.add_memory(mems[mid])
        index_store.save(index)
        return {"status": "sync_completed"}
