import uuid
from crdt.orset import ORSet
from crdt.lww import LWWRegister

from crdt.orset import ORSet
from crdt.lww import LWWRegister
from runtime.clocks import Dot

class MemoryActor:
    def __init__(self, id, owner_id, content, memory_type, tags=None, **kwargs):
        self.id = id
        self.owner_id = owner_id
        self.content = LWWRegister(content)
        self.memory_type = LWWRegister(memory_type)
        self.tags = ORSet(tags or [])
        self.status = LWWRegister("active")
        self.embedding = LWWRegister([]) # 存储向量

        # _meta 现在包含版本向量版本
        default_meta = {
            "actor_id": id,
            "revision": 0,
            "clock": 0,
            "version_vector": {}
        }
        self._meta = kwargs.get("_meta", default_meta)
        if "version_vector" not in self._meta:
            self._meta["version_vector"] = {}

        self._deleted = kwargs.get("_deleted", False)
        self.delete_certificate = kwargs.get("delete_certificate", None)

    def apply(self, message, context):
        """处理消息并更新内部 CRDT 状态"""
        mtype = message.type
        payload = message.payload
        clock = message.clock
        node_id = message.node_id
        # 生成基于 node:actor:counter 的唯一 Dot
        dot = str(Dot(node_id, self.id, clock))

        if mtype == "update_content":
            self.content.set(payload["content"], clock, node_id)
        elif mtype == "update_type":
            self.memory_type.set(payload["type"], clock, node_id)
        elif mtype == "add_tag":
            self.tags.add(payload["tag"], dot)
        elif mtype == "remove_tag":
            self.tags.remove(payload["tag"], dot)
        elif mtype == "set_status":
            self.status.set(payload["status"], clock, node_id)
        elif mtype == "update_embedding":
            self.embedding.set(payload["embedding"], clock, node_id)
        elif mtype == "delete":
            self._deleted = True
            self.delete_certificate = payload.get("certificate")

        # 更新元数据
        self._meta["clock"] = max(self._meta.get("clock", 0), clock)
        self._meta["revision"] = context.next_revision()
        # 更新版本向量 (Version Vector)
        vv = self._meta["version_vector"]
        vv[node_id] = max(vv.get(node_id, 0), clock)

    def merge_state(self, remote_dict, cert_index=None):
        """合并远程状态到本地，包含复活防御逻辑"""
        # 1. 检查复活防御 (Delete Certificate Dominance)
        # 如果本地已有该对象的删除证书，或者父级作用域已删除，则保持删除状态
        if cert_index:
            # 这里的 scope_path 我们简单构建下
            scopes = [f"user:{self.owner_id}", self.id]
            if cert_index.find_covering(scopes):
                self._deleted = True
                return

        # 2. 如果远程状态已经标记删除
        if remote_dict.get("_deleted"):
            self._deleted = True
            if remote_dict.get("delete_certificate"):
                self.delete_certificate = remote_dict["delete_certificate"]
            return

        # 3. 正常字段合并
        if "content" in remote_dict:
            self.content.merge(remote_dict["content"])
        if "memory_type" in remote_dict:
            self.memory_type.merge(remote_dict["memory_type"])
        if "tags" in remote_dict:
            self.tags.merge(remote_dict["tags"])
        if "status" in remote_dict:
            self.status.merge(remote_dict["status"])
        if "embedding" in remote_dict:
            self.embedding.merge(remote_dict["embedding"])

        # 4. 合并元数据
        remote_meta = remote_dict.get("_meta", {})
        self._meta["clock"] = max(self._meta.get("clock", 0), remote_meta.get("clock", 0))
        self._meta["revision"] += 1 # 状态变更增加本地版本

        # 5. 合并版本向量 (Version Vector)
        remote_vv = remote_meta.get("version_vector", {})
        for rid, rclock in remote_vv.items():
            self._meta["version_vector"][rid] = max(self._meta["version_vector"].get(rid, 0), rclock)

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "content": self.content.to_dict(),
            "memory_type": self.memory_type.to_dict(),
            "tags": self.tags.to_dict(),
            "status": self.status.to_dict(),
            "embedding": self.embedding.to_dict(),
            "_meta": self._meta,
            "_deleted": self._deleted,
            "delete_certificate": self.delete_certificate
        }

class IndexActor:
    def __init__(self):
        self.owner_index = {}    # user -> [memory_ids]
        self.tag_index = {}      # tag -> [memory_ids]
        self.type_index = {}     # type -> [memory_ids]
        self.vector_store = {}   # memory_id -> vector (list)

    def add_memory(self, mem):
        self.owner_index.setdefault(mem.owner_id, set()).add(mem.id)
        for tag in mem.tags.elements():
            self.tag_index.setdefault(tag, set()).add(mem.id)
        self.type_index.setdefault(mem.memory_type.value, set()).add(mem.id)
        if hasattr(mem, "embedding") and mem.embedding.value:
            self.vector_store[mem.id] = mem.embedding.value

    def remove_memory(self, mem):
        self.owner_index.get(mem.owner_id, set()).discard(mem.id)
        for tag in mem.tags.elements():
            self.tag_index.get(tag, set()).discard(mem.id)
        self.type_index.get(mem.memory_type.value, set()).discard(mem.id)
        self.vector_store.pop(mem.id, None)

    def query(self, owner=None, tag=None, type_=None):
        results = None
        if owner:
            results = self.owner_index.get(owner, set()).copy()
        if tag:
            tag_results = self.tag_index.get(tag, set()).copy()
            results = tag_results if results is None else results & tag_results
        if type_:
            type_results = self.type_index.get(type_, set()).copy()
            results = type_results if results is None else results & type_results
        return list(results) if results is not None else []

    def hybrid_query(self, owner=None, tag=None, query_text=None, provider=None, top_k=5):
        from runtime.embeddings import cosine_similarity
        # 1. 硬约束过滤
        candidates = self.query(owner=owner, tag=tag)
        if not candidates:
            return []

        if not query_text or not provider:
            return [(cid, 1.0) for cid in candidates[:top_k]]

        # 2. 软约束排序
        query_vec = provider.get_embedding(query_text)
        scores = []
        for cid in candidates:
            vec = self.vector_store.get(cid)
            if vec:
                sim = cosine_similarity(query_vec, vec)
                scores.append((cid, sim))
            else:
                scores.append((cid, 0.0))

        # 按相似度排序
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
