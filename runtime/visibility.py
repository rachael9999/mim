class DeleteCertIndex:
    def __init__(self):
        self.by_scope = {}

    def add(self, cert):
        if "timestamp" not in cert:
            import time
            cert["timestamp"] = time.time()
        self.by_scope[cert["scope"]] = cert

    def cleanup_tombstones(self, ttl_seconds):
        """删除超过 TTL 的证书"""
        import time
        now = time.time()
        expired = [s for s, c in self.by_scope.items() if now - c.get("timestamp", 0) > ttl_seconds]
        for s in expired:
            del self.by_scope[s]
        return len(expired)

    def find_covering(self, scope_path):
        for scope in scope_path:
            if scope in self.by_scope:
                return self.by_scope[scope]
            # 支持通配符或前缀匹配 (例如 user:* )
            # 这里的逻辑可以根据需要增强
        return None

    def to_dict(self):
        return self.by_scope

    def from_dict(self, data):
        self.by_scope = data

class DummyScopeGraph:
    def ancestor_chain(self, actor):
        # 建立层级链: user -> memory
        res = []
        if hasattr(actor, "owner_id") and actor.owner_id:
            res.append(f"user:{actor.owner_id}")
        res.append(actor.id)
        return res

class VisibilityResolver:
    def __init__(self, cert_index, scope_graph):
        self.cert_index = cert_index
        self.scope_graph = scope_graph

    def object_visible(self, actor):
        """双层可见性过滤"""
        # 1. 强制 Control-Plane 过滤 (Certificate dominance)
        # 只要存在任何父级或对象本身的删除证书，对象立即失效
        scopes = self.scope_graph.ancestor_chain(actor)
        cert = self.cert_index.find_covering(scopes)
        if cert:
            # TODO: 这里未来可以触发物理清理 (Compaction)
            return False

        # 2. 检查 Data-Plane 状态 (LWW Logic Deletion)
        if getattr(actor, "_deleted", False):
            return False

        # 3. 业务状态过滤
        status = getattr(actor, "status", None)
        if hasattr(status, "value") and status.value == "archived":
            return False

        return True

    def link_visible(self, from_actor, to_id):
        """图谱关系可见性校验: 确保不会返回指向已删除节点的断头边"""
        # 1. 源节点必须可见
        if not self.object_visible(from_actor):
            return False

        # 2. 目标节点必须存在且可见
        from runtime.core import mems
        target_actor = mems.get(to_id)
        if not target_actor:
            return False

        if not self.object_visible(target_actor):
            return False

        return True
