import os
import time
from runtime.context import ActorContext
from runtime.message import Message
from runtime.oplog import Oplog
from runtime.actor import MemoryActor

class MimRuntime:
    def __init__(self, actor_store, index_actor, cert_index, snapshot_dir="mim/snapshots", embedding_provider=None):
        import json
        from runtime.gc import EpochGate
        self.store = actor_store
        self.index = index_actor
        self.cert_index = cert_index
        self.snapshot_dir = snapshot_dir
        self.oplogs = {} # actor_id -> Oplog
        self.embedding_provider = embedding_provider
        self.processed_message_ids = set()
        self.epoch_gate = EpochGate() # 默认允许所有
        self._load_processed_ids()

    def _load_processed_ids(self):
        import json
        path = os.path.join(self.snapshot_dir, "processed_messages.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                self.processed_message_ids = set(json.load(f))

    def _save_processed_ids(self):
        import json
        path = os.path.join(self.snapshot_dir, "processed_messages.json")
        with open(path, "w") as f:
            json.dump(list(self.processed_message_ids), f)

    def _get_oplog(self, actor_id):
        if actor_id not in self.oplogs:
            path = os.path.join(self.snapshot_dir, "oplogs", f"{actor_id}.log")
            self.oplogs[actor_id] = Oplog(path)
        return self.oplogs[actor_id]

    def dispatch(self, actor, mtype, payload, node_id=None):
        """Merge Pipeline: Control-Plane (Certs) -> Data-Plane (Actor)"""
        if node_id is None:
            from runtime.core import NODE_ID
            node_id = NODE_ID

        # 0. 强制前置 Certificate 检查 (Epoch Gate / Visibility Check)
        from runtime.visibility import VisibilityResolver
        from runtime.core import cert_index, scope_graph
        vis = VisibilityResolver(cert_index, scope_graph)

        if not vis.object_visible(actor) and mtype != "delete":
            # 如果对象对当前节点不可见（已被 Cert 覆盖），拒绝非删除类更新
            print(f"[DISPATCH] Rejected update for {actor.id}: Object is invisible/deleted by certificate.")
            return actor

        # 0.1 Epoch Gate Check (P10-2)
        # 如果是外部同步或某些需要检查时钟的操作
        if "clock" in payload and not self.epoch_gate.is_allowed(payload["clock"]):
            print(f"[DISPATCH] Rejected update for {actor.id}: Clock {payload['clock']} is below epoch gate.")
            return actor

        # 1. 创建 Context
        ctx = ActorContext(actor.id, node_id=node_id)
        ctx.update_from_actor(actor._meta)

        # 2. 创建消息并递增时钟
        msg = Message(mtype, payload, node_id=node_id, clock=ctx.next_clock())

        # 3. 写入 Oplog (WAL)
        oplog = self._get_oplog(actor.id)
        oplog.append(msg)

        # 4. 应用到 Actor
        actor.apply(msg, ctx)

        # 5. 原子化保存快照
        self.store.save(actor)

        # 6. Checkpoint: 截断 Oplog
        oplog.truncate()

        # 7. 更新索引 (如果是影响索引的操作)
        self.index.add_memory(actor)

        # 8. 派生任务: 如果更新了内容，自动生成 embedding
        if mtype == "update_content" and self.embedding_provider:
            embedding = self.embedding_provider.get_embedding(payload["content"])
            # 自动发送 update_embedding 消息
            self.dispatch(actor, "update_embedding", {"embedding": embedding}, node_id=node_id)

        # 9. P13: 主动复制 (Broadcast to Peers)
        # 只有本地产生的非派生消息才触发广播，避免广播风暴
        if node_id == self._get_local_node_id() and mtype not in ["update_embedding"]:
            self._broadcast_update(actor)

        return actor

    def _get_local_node_id(self):
        from runtime.core import NODE_ID
        return NODE_ID

    def _broadcast_update(self, actor):
        """异步将更新推送到 Peer 节点"""
        import threading
        from runtime.core import get_peers
        peers = get_peers()
        if not peers:
            return

        def push_to_peers():
            import requests
            data = actor.to_dict()
            for peer_url in peers:
                try:
                    # 复用 sync 逻辑进行推送
                    requests.post(f"{peer_url}/v1/sync_single", json=data, timeout=2)
                except:
                    pass

        threading.Thread(target=push_to_peers, daemon=True).start()

    def recover_actor(self, actor, node_id="local"):
        """重启时恢复未完成的 oplog"""
        oplog = self._get_oplog(actor.id)
        messages = oplog.read_all()
        if not messages:
            return actor

        print(f"[RECOVERY] Replaying {len(messages)} messages for {actor.id}")
        ctx = ActorContext(actor.id, node_id=node_id)
        ctx.update_from_actor(actor._meta)

        for msg in messages:
            actor.apply(msg, ctx)

        # 重新保存并清理
        self.store.save(actor)
        oplog.truncate()
        return actor

    def maintain(self, current_time=None, k=0.0001, cold_threshold=0.5, delete_threshold=0.1, cert_ttl=86400*30):
        """维护周期: 处理衰减、归档、删除和证书清理"""
        from runtime.gc import GCCoordinator
        coordinator = GCCoordinator(self, self.cert_index, cert_ttl)

        # 1. 运行 GC 协调器 (处理过期证书和物理压缩)
        coordinator.run_gc_cycle()

        # 2. 处理所有 Actor 的状态迁移
        if current_time is None:
            current_time = time.time()

        from runtime.core import mems
        for mid, actor in list(mems.items()):
            if actor._deleted:
                continue

            importance = actor.calculate_current_importance(current_time, k)
            status = actor.status.value

            if status == "active" and importance < cold_threshold:
                print(f"[MAINTAIN] Archiving {mid} (importance: {importance:.4f})")
                self.dispatch(actor, "set_status", {"status": "archived"})

            elif status == "archived" and importance < delete_threshold:
                print(f"[MAINTAIN] Deleting {mid} (importance: {importance:.4f})")
                # 触发逻辑删除
                from runtime.core import NODE_ID
                cert = {"scope": mid, "delete_clock": {NODE_ID: 1}, "policy": "delete_wins", "timestamp": current_time}
                self.dispatch(actor, "delete", {"certificate": cert})
                self.cert_index.add(cert)

        print("[MAINTAIN] Maintenance completed.")

    def create_actor_if_not_exists(self, actor_id, user_id, content, memory_type):
        """确保 Actor 存在，如果不存在则创建"""
        from runtime.core import mems
        if actor_id in mems:
            return mems[actor_id]

        mem = MemoryActor(id=actor_id, owner_id=user_id, content="", memory_type=memory_type, tags=[])
        mems[actor_id] = mem
        self.dispatch(mem, "update_content", {"content": content})
        self.index.add_memory(mem)
        return mem

    def graph_query(self, user_id, query_text, max_hops=3, hop_decay=0.6):
        """Spreading Activation 能量扩散搜索 (增强版)"""
        print(f"[GRAPH] Spreading activation for: '{query_text}' (User: {user_id})")

        # 关系权重配置 (P14 增强)
        REL_WEIGHTS = {
            "Produces": 1.0,
            "INTEGRATED_IN": 0.9,
            "contained_in": 0.8,
            "RelatedTo": 0.7,
            "mentions": 0.4,
            "occurs_in": 0.6,
            "parent_of": 0.5,
            "contains": 0.3
        }

        # 1. 种子节点: 语义搜索获取初始能量
        initial_seeds = self.index.hybrid_query(owner=user_id, query_text=query_text, provider=self.embedding_provider, top_k=5)
        if not initial_seeds:
            return []

        # active_nodes: actor_id -> energy
        active_nodes = {mid: score for mid, score in initial_seeds}
        final_scores = active_nodes.copy()
        paths = {mid: [mid] for mid in active_nodes} # 追踪推理路径

        # 2. 扩散循环
        from runtime.core import mems
        for hop in range(max_hops):
            new_activations = {}
            for mid, energy in active_nodes.items():
                actor = mems.get(mid)
                if not actor or actor._deleted:
                    continue

                # 能量根据重要性加成 (Importance-Driven)
                importance = actor.calculate_current_importance()
                # 基础传播能量 = 当前能量 * 节点重要性 * 衰减系数
                base_spread = energy * (0.5 + 0.5 * importance) * hop_decay

                # 传播到邻居
                links = actor.links.elements()
                for (to_id, rel_type, weight) in links:
                    if to_id == mid: continue # 避开自环

                    # 结合关系权重
                    rel_gain = REL_WEIGHTS.get(rel_type, 0.5)
                    contribution = base_spread * weight * rel_gain

                    if contribution > 0.01: # 能量阈值拦截，防止无限微弱扩散
                        new_activations[to_id] = new_activations.get(to_id, 0) + contribution
                        if to_id not in paths:
                            paths[to_id] = paths[mid] + [to_id]

            if not new_activations:
                break

            # 合并能量到最终得分
            for mid, energy in new_activations.items():
                final_scores[mid] = final_scores.get(mid, 0) + energy

            active_nodes = new_activations

        # 排序并过滤掉已删除节点
        results = []
        from runtime.visibility import VisibilityResolver
        from runtime.core import cert_index, scope_graph
        vis = VisibilityResolver(cert_index, scope_graph)

        for mid, score in final_scores.items():
            actor = mems.get(mid)
            if actor and vis.object_visible(actor):
                results.append({
                    "id": mid,
                    "score": score,
                    "content": actor.content.value,
                    "path": " -> ".join(paths.get(mid, []))
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def discover_insights(self, user_id, top_n=5):
        """知识发现：识别紧密关联的集群并使用并发总结 (P15 优化版)"""
        print(f"[DISCOVERY] Running optimized discovery for user: {user_id}")
        from runtime.core import mems, llm_extractor
        from concurrent.futures import ThreadPoolExecutor
        import hashlib

        # 1. 识别集群中心
        centers = []
        for mid, actor in mems.items():
            if actor.owner_id == user_id and not actor._deleted and actor.memory_type.value != "insight":
                links = actor.links.elements()
                if len(links) >= 2:
                    centers.append((mid, len(links)))

        centers.sort(key=lambda x: x[1], reverse=True)

        tasks = []
        cluster_info = []

        # 2. 准备集群任务
        for center_id, count in centers[:top_n]:
            center_actor = mems.get(center_id)
            cluster_mems = [center_actor.content.value]
            cluster_ids = [center_id]

            links = center_actor.links.elements()
            for (to_id, rel, w) in links:
                neighbor = mems.get(to_id)
                if neighbor and not neighbor._deleted:
                    cluster_mems.append(neighbor.content.value)
                    cluster_ids.append(to_id)

            if len(cluster_mems) >= 2:
                # 生成集群指纹，用于去重
                cluster_mems.sort()
                fingerprint = hashlib.md5("".join(cluster_mems).encode()).hexdigest()

                cluster_info.append({
                    "ids": cluster_ids,
                    "texts": cluster_mems,
                    "fingerprint": fingerprint
                })
                tasks.append(cluster_mems)

        if not tasks:
            return []

        # 3. 并发执行 LLM 总结
        print(f"[DISCOVERY] Sending {len(tasks)} clusters to LLM concurrently...")
        insights = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(llm_extractor.summarize_cluster, tasks))

        # 4. 回写结果
        for i, summary in enumerate(results):
            if summary:
                info = cluster_info[i]
                # 检查是否已经存在相同的 Insight (简单指纹匹配)
                insight_id = f"insight_{info['fingerprint'][:12]}"
                if insight_id not in mems:
                    insight_mem = self.create_actor_if_not_exists(
                        insight_id, user_id, f"Insight: {summary}", "insight"
                    )
                    for mid in info["ids"]:
                        self.dispatch(insight_mem, "add_link", {"to_id": mid, "type": "summarizes", "weight": 0.8})

                insights.append(summary)

        return list(set(insights)) # 去重返回
    def ingest_dialogue(self, user_id, messages, extractor):
        """从对话中提取并摄入记忆 (带去重)"""
        # 1. 过滤已处理的消息
        new_messages = [m for m in messages if m.message_id not in self.processed_message_ids]
        if not new_messages:
            print("[INGEST] No new messages to process.")
            return []

        print(f"[INGEST] Processing {len(new_messages)} new messages for user {user_id}")

        # 2. 提取操作
        ops = extractor.extract_memories(new_messages)

        results = []
        for op in ops:
            # 3. 创建新的 MemoryActor
            mem_id = f"mem_ext_{int(time.time()*1000)}_{len(results)}"
            mem = MemoryActor(id=mem_id, owner_id=user_id, content="", memory_type=op.memory_type, tags=[])

            # 4. 调度更新
            self.dispatch(mem, "update_content", {"content": op.content})
            for tag in op.tags:
                self.dispatch(mem, "add_tag", {"tag": tag})

            # 4.1 处理提取出的链接
            for link in op.links:
                self.dispatch(mem, "add_link", {
                    "to_id": link["to_id"],
                    "type": link["type"],
                    "weight": link.get("weight", 0.8)
                })

            results.append(mem)
            print(f"[INGEST] Extracted: {op.content} -> {mem_id}")

        # 5. 标记消息为已处理
        for m in new_messages:
            self.processed_message_ids.add(m.message_id)
        self._save_processed_ids()

        return results
