from runtime.clocks import LamportClock

class ActorContext:
    def __init__(self, actor_id, node_id="local", lamport=0, revision=0):
        self.actor_id = actor_id
        self.node_id = node_id
        self.clock = LamportClock(lamport, node_id)
        self.revision = revision

    def next_clock(self):
        return self.clock.tick().lamport

    def merge_clock(self, remote_lamport):
        return self.clock.merge(remote_lamport).lamport

    def next_revision(self):
        self.revision += 1
        return self.revision

    def update_from_actor(self, meta):
        self.clock.lamport = max(self.clock.lamport, meta.get("clock", 0))
        self.revision = meta.get("revision", self.revision)

    def to_dict(self):
        return {
            "actor_id": self.actor_id,
            "node_id": self.node_id,
            "clock": self.clock,
            "revision": self.revision
        }
