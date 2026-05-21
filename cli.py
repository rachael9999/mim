import sys
import os
import json
import time
from runtime.core import mems, index, cert_index, scope_graph, store, index_store, embed_provider, runtime, restore_all, save_certs, SNAPSHOT_DIR
from runtime.actor import MemoryActor
from runtime.visibility import VisibilityResolver
from runtime.extractor import DialogueMessage, MockExtractor

def remember(user, content, type_="project", tag="mim"):
    mem_id = f"mem_{int(time.time()*1000)}"
    mem = MemoryActor(id=mem_id, owner_id=user, content="", memory_type=type_, tags=[])
    mems[mem_id] = mem
    runtime.dispatch(mem, "update_content", {"content": content})
    runtime.dispatch(mem, "add_tag", {"tag": tag})
    index_store.save(index)
    print(f"[CREATE] {mem_id}: {content}")

def recall(user, tag=None):
    vis = VisibilityResolver(cert_index, scope_graph)
    ids = index.query(owner=user, tag=tag)
    found = False
    for mid in ids:
        mem = mems.get(mid)
        if mem and vis.object_visible(mem):
            print(f"[{mem.id}] ({mem.memory_type.value}) {mem.content.value} (clock:{mem._meta.get('clock')})")
            found = True
    if not found:
        print("No memories found.")

def search(user, query_text):
    print(f"[SEARCH] Searching for: '{query_text}' (User: {user})")
    results = index.hybrid_query(owner=user, query_text=query_text, provider=embed_provider)
    found = False
    for mid, score in results:
        mem = mems.get(mid)
        if mem:
            print(f"[{score:.4f}] [{mem.id}] ({mem.memory_type.value}) {mem.content.value}")
            found = True
    if not found:
        print("No matches found.")

def forget(mem_id):
    mem = mems.get(mem_id)
    if not mem:
        print(f"Memory {mem_id} not found.")
        return
    cert = {"scope": mem_id, "delete_clock": {"local": 1}, "policy": "delete_wins"}
    runtime.dispatch(mem, "delete", {"certificate": cert})
    cert_index.add(cert)
    save_certs()
    print(f"[FORGET] {mem_id}")

def sync(source_node_dir):
    print(f"[SYNC] Syncing from {source_node_dir}...")
    remote_cert_file = os.path.join(source_node_dir, "certs.json")
    if os.path.exists(remote_cert_file):
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
    print(f"[SYNC] Sync completed.")

def ingest(user, text):
    extractor = MockExtractor()
    if os.path.exists(text):
        with open(text, "r", encoding="utf-8") as f:
            data = json.load(f)
            messages = [DialogueMessage(**m) for m in data]
    else:
        messages = [DialogueMessage(role="user", content=text)]
    extracted = runtime.ingest_dialogue(user, messages, extractor)
    for mem in extracted:
        mems[mem.id] = mem
    index_store.save(index)
    print(f"[INGEST] Completed ingestion for {user}. Extracted {len(extracted)} memories.")

if __name__ == "__main__":
    restore_all()
    if len(sys.argv) < 2:
        print("Usage: python cli.py <cmd> [args...]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "remember": remember(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv)>4 else "project", sys.argv[5] if len(sys.argv)>5 else "mim")
    elif cmd == "recall": recall(sys.argv[2], sys.argv[3] if len(sys.argv)>3 else None)
    elif cmd == "search": search(sys.argv[2], sys.argv[3])
    elif cmd == "forget": forget(sys.argv[2])
    elif cmd == "sync": sync(sys.argv[2])
    elif cmd == "ingest": ingest(sys.argv[2], sys.argv[3])
    else: print("Commands: remember, recall, search, forget, sync, ingest")
