import time
import os
import json

class GCCoordinator:
    def __init__(self, runtime, cert_index, cert_ttl=86400*30):
        self.runtime = runtime
        self.cert_index = cert_index
        self.cert_ttl = cert_ttl
        self.stable_watermark = {} # node_id -> last_stable_clock

    def run_gc_cycle(self):
        """执行 GC 周期：清理过期证书和压缩已删除 Actor"""
        print("[GC] Starting GC coordinator cycle...")

        # 1. 清理过期证书 (Tombstones)
        removed_count = self.cert_index.cleanup_tombstones(self.cert_ttl)
        if removed_count > 0:
            print(f"[GC] Purged {removed_count} expired certificates.")

        # 2. 物理压缩 (Compaction)
        # 找出那些被证书覆盖且已逻辑删除的 Actor 文件，执行物理删除
        from runtime.core import mems, store
        purged_actors = 0
        for mid in list(mems.keys()):
            actor = mems[mid]
            # 如果双层过滤判定为不可见且标记为 _deleted，则可以物理删除快照
            from runtime.visibility import VisibilityResolver
            from runtime.core import scope_graph
            vis = VisibilityResolver(self.cert_index, scope_graph)

            if not vis.object_visible(actor) and actor._deleted:
                # 物理删除
                store.delete(mid)
                del mems[mid]
                purged_actors += 1

        if purged_actors > 0:
            print(f"[GC] Physically compacted {purged_actors} actors.")

        print("[GC] GC cycle completed.")

class EpochGate:
    """防止旧副本回流的门控"""
    def __init__(self, min_allowed_clock=0):
        self.min_allowed_clock = min_allowed_clock

    def is_allowed(self, incoming_clock):
        # 如果时钟早于我们已经完全清理并归档的阈值，拒绝 direct merge
        # 这要求客户端进行 full resync
        return incoming_clock >= self.min_allowed_clock
