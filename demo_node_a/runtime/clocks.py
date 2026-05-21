import time
import os
import binascii

class LamportClock:
    def __init__(self, lamport=0, node_id="local"):
        self.lamport = lamport
        self.node_id = node_id

    def tick(self):
        self.lamport += 1
        return self

    def merge(self, remote_lamport):
        self.lamport = max(self.lamport, remote_lamport) + 1
        return self

    def to_tuple(self):
        return (self.lamport, self.node_id)

    def to_dict(self):
        return {"lamport": self.lamport, "node_id": self.node_id}

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, int): # 兼容旧版整数时钟
            return cls(lamport=data)
        return cls(lamport=data.get("lamport", 0), node_id=data.get("node_id", "local"))

class Dot:
    def __init__(self, node_id, actor_id, counter):
        self.node_id = node_id
        self.actor_id = actor_id
        self.counter = counter

    def __str__(self):
        return f"{self.node_id}:{self.actor_id}:{self.counter}"

def generate_ulid():
    """极简版可用作排序的唯一 ID (timestamp + random)"""
    ts = int(time.time() * 1000)
    rand = binascii.hexlify(os.urandom(5)).decode()
    return f"{ts:014x}{rand}"
