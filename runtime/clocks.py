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

class VersionVector:
    def __init__(self, dots=None):
        # node_id -> counter
        self.vector = dots or {}

    def increment(self, node_id):
        self.vector[node_id] = self.vector.get(node_id, 0) + 1
        return self.vector[node_id]

    def set(self, node_id, counter):
        self.vector[node_id] = max(self.vector.get(node_id, 0), counter)

    def merge(self, other):
        # other can be a VersionVector or a dict
        other_vec = other.vector if isinstance(other, VersionVector) else other
        for node_id, counter in other_vec.items():
            self.set(node_id, counter)

    def dominates(self, other):
        """If this vector is >= other in all nodes (Partial Order)"""
        other_vec = other.vector if isinstance(other, VersionVector) else other
        for node_id, counter in other_vec.items():
            if self.vector.get(node_id, 0) < counter:
                return False
        return True

    def compare(self, other):
        """
        Returns:
        1 if self > other
        -1 if self < other
        0 if self == other
        None if concurrent (conflict)
        """
        self_greater = False
        other_greater = False

        all_nodes = set(self.vector.keys()) | set(other.vector.keys())
        for node_id in all_nodes:
            v1 = self.vector.get(node_id, 0)
            v2 = other.vector.get(node_id, 0)
            if v1 > v2:
                self_greater = True
            elif v1 < v2:
                other_greater = True

        if self_greater and not other_greater: return 1
        if other_greater and not self_greater: return -1
        if not self_greater and not other_greater: return 0
        return None # Concurrent

    def to_dict(self):
        return self.vector.copy()

    @classmethod
    def from_dict(cls, data):
        return cls(dots=data.copy())

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
