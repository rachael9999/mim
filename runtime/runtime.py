import os
import time
from runtime.context import ActorContext
from runtime.message import Message
from runtime.oplog import Oplog
from runtime.actor import MemoryActor

class MimRuntime:
    def __init__(self, actor_store, index_actor, cert_index, snapshot_dir="mim/snapshots", embedding_provider=None):
        import json
        self.store = actor_store
        self.index = index_actor
        self.cert_index = cert_index
        self.snapshot_dir = snapshot_dir
        self.oplogs = {} # actor_id -> Oplog
        self.embedding_provider = embedding_provider
        self.processed_message_ids = set()
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

    def dispatch(self, actor, mtype, payload, node_id="local"):
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

        return actor

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

            results.append(mem)
            print(f"[INGEST] Extracted: {op.content} -> {mem_id}")

        # 5. 标记消息为已处理
        for m in new_messages:
            self.processed_message_ids.add(m.message_id)
        self._save_processed_ids()

        return results
