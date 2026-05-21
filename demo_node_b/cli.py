import sys
import os
import json
from runtime.actor import MemoryActor, IndexActor
from runtime.visibility import DeleteCertIndex, DummyScopeGraph, VisibilityResolver
from runtime.snapshot_store import SnapshotStore
from runtime.index_snapshot import IndexSnapshotStore

SNAPSHOT_DIR = "mim/snapshots"
CERT_FILE = os.path.join(SNAPSHOT_DIR, "certs.json")

mems = {}        # id -> MemoryActor
index = IndexActor()
cert_index = DeleteCertIndex()
scope_graph = DummyScopeGraph()
store = SnapshotStore(SNAPSHOT_DIR)
index_store = IndexSnapshotStore(os.path.join(SNAPSHOT_DIR, "index.json"))

# --- 恢复持久化状态 ---
def restore_all():
    # 1. 恢复证书
    if os.path.exists(CERT_FILE):
        with open(CERT_FILE, "r", encoding="utf-8") as f:
            cert_index.from_dict(json.load(f))

    # 2. 恢复 MemoryActors
    if os.path.exists(SNAPSHOT_DIR):
        for fn in os.listdir(SNAPSHOT_DIR):
            if fn.endswith(".json") and not (fn.startswith("index") or fn == "certs.json"):
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
                    # 恢复状态字段
                    if "status" in data:
                        mem.status.set(data["status"]["value"])
                    mems[mid] = mem

    # 3. 恢复 Index
    index_store.load(index)

def save_certs():
    with open(CERT_FILE, "w", encoding="utf-8") as f:
        json.dump(cert_index.to_dict(), f, ensure_ascii=False, indent=2)

from runtime.runtime import MimRuntime

# ... (保留现有变量定义)

runtime = MimRuntime(store, index, cert_index, SNAPSHOT_DIR)

# --- 恢复持久化状态 ---
def restore_all():
    # 1. 恢复证书
    if os.path.exists(CERT_FILE):
        with open(CERT_FILE, "r", encoding="utf-8") as f:
            cert_index.from_dict(json.load(f))

    # 2. 恢复 MemoryActors 并进行故障恢复
    if os.path.exists(SNAPSHOT_DIR):
        for fn in os.listdir(SNAPSHOT_DIR):
            if fn.endswith(".json") and not (fn.startswith("index") or fn == "certs.json"):
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

                    # --- P5 故障恢复 ---
                    runtime.recover_actor(mem)

                    mems[mid] = mem

    # 3. 恢复 Index
    index_store.load(index)

# ... (save_certs 等函数保持不变)

def remember(user, content, type_="project", tag="mim"):
    import time
    mem_id = f"mem_{int(time.time()*1000)}"
    # 创建初始 actor
    mem = MemoryActor(id=mem_id, owner_id=user, content="", memory_type=type_, tags=[])
    mems[mem_id] = mem

    # 通过 runtime 调度更新 (会自动记录 oplog, apply, save)
    runtime.dispatch(mem, "update_content", {"content": content})
    runtime.dispatch(mem, "add_tag", {"tag": tag})

    index_store.save(index)
    print(f"[CREATE] {mem_id}: {content}")

def recall(user, query=None):
    vis = VisibilityResolver(cert_index, scope_graph)
    ids = index.query(owner=user, tag=query)
    found = False
    for mid in ids:
        mem = mems.get(mid)
        if mem and vis.object_visible(mem):
            print(f"[{mem.id}] ({mem.memory_type.value}) {mem.content.value} (clock:{mem._meta.get('clock')})")
            found = True
    if not found:
        print("No memories found.")

def forget(mem_id):
    mem = mems.get(mem_id)
    if not mem:
        print(f"Memory {mem_id} not found.")
        return

    cert = {
        "scope": mem_id,
        "delete_clock": {"local": 1},
        "policy": "delete_wins"
    }
    runtime.dispatch(mem, "delete", {"certificate": cert})
    cert_index.add(cert) # 确保同步到全局索引

    save_certs()
    print(f"[FORGET] {mem_id}")

def archive(mem_id):
    mem = mems.get(mem_id)
    if not mem:
        print(f"Memory {mem_id} not found.")
        return
    runtime.dispatch(mem, "set_status", {"status": "archived"})
    print(f"[ARCHIVE] {mem_id}")

# ... (delete_user 保持不变)

def delete_user(user_id):
    # 生成 User 级 Delete Certificate (层级删除演示)
    cert = {
        "scope": f"user:{user_id}",
        "delete_clock": {"local": 1},
        "policy": "delete_wins"
    }
    cert_index.add(cert)
    save_certs()
    print(f"[DELETE USER] {user_id} - all child memories will be hidden.")

def sync(source_node_dir):
    print(f"[SYNC] Syncing from {source_node_dir}...")
    # 1. 恢复远程证书
    remote_cert_file = os.path.join(source_node_dir, "certs.json")
    if os.path.exists(remote_cert_file):
        with open(remote_cert_file, "r", encoding="utf-8") as f:
            remote_certs = json.load(f)
            for scope, cert in remote_certs.items():
                cert_index.add(cert)
        save_certs()

    # 2. 遍历远程快照并合并
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
                    # 如果本地不存在，初始化一个新的 Actor
                    mems[mid] = MemoryActor(
                        id=remote_data["id"],
                        owner_id=remote_data["owner_id"],
                        content="",
                        memory_type=remote_data["memory_type"]["value"],
                        tags=[]
                    )
                    mems[mid].merge_state(remote_data, cert_index)

                # 保存合并后的结果
                store.save(mems[mid])
                index.add_memory(mems[mid])

    index_store.save(index)
    print(f"[SYNC] Sync completed.")

if __name__ == "__main__":
    restore_all()
    if len(sys.argv) < 2:
        print("Usage: python cli.py <cmd> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "remember":
        remember(sys.argv[2], sys.argv[3],
                 sys.argv[4] if len(sys.argv)>4 else "project",
                 sys.argv[5] if len(sys.argv)>5 else "mim")
    elif cmd == "recall":
        recall(sys.argv[2], sys.argv[3] if len(sys.argv)>3 else None)
    elif cmd == "forget":
        forget(sys.argv[2])
    elif cmd == "archive":
        archive(sys.argv[2])
    elif cmd == "delete_user":
        delete_user(sys.argv[2])
    elif cmd == "sync":
        sync(sys.argv[2])
    else:
        print("Commands: remember, recall, forget, archive, delete_user, sync")
