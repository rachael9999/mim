class DeleteCertIndex:
    def __init__(self):
        self.by_scope = {}

    def add(self, cert):
        self.by_scope[cert["scope"]] = cert

    def find_covering(self, scope_path):
        for scope in scope_path:
            if scope in self.by_scope:
                return self.by_scope[scope]
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
        # 1. 检查父级及本体是否有 Delete Certificate
        scopes = self.scope_graph.ancestor_chain(actor)
        cert = self.cert_index.find_covering(scopes)
        if cert:
            return False

        # 2. 检查逻辑删除标记
        if getattr(actor, "_deleted", False):
            return False

        # 3. 检查 LWW 状态 (如 archived)
        status = getattr(actor, "status", None)
        if hasattr(status, "value") and status.value == "archived":
            return False

        return True
