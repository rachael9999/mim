import os
from runtime.context import ActorContext
from runtime.message import Message
from runtime.oplog import Oplog

class MimRuntime:
    def __init__(self, actor_store, index_actor, cert_index, snapshot_dir="mim/snapshots"):
        self.store = actor_store
        self.index = index_actor
        self.cert_index = cert_index
        self.snapshot_dir = snapshot_dir
        self.oplogs = {} # actor_id -> Oplog

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
