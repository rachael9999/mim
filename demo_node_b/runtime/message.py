import time
from runtime.clocks import generate_ulid

class Message:
    def __init__(self, type, payload, node_id="local", clock=0, timestamp=None, message_id=None):
        self.type = type
        self.payload = payload
        self.node_id = node_id
        self.clock = clock # 这里的 clock 指的是 Lamport Clock
        self.timestamp = timestamp or time.time()
        self.message_id = message_id or generate_ulid()

    def to_dict(self):
        return {
            "type": self.type,
            "payload": self.payload,
            "node_id": self.node_id,
            "clock": self.clock,
            "timestamp": self.timestamp,
            "message_id": self.message_id
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            type=data["type"],
            payload=data["payload"],
            node_id=data.get("node_id", "local"),
            clock=data.get("clock", 0),
            timestamp=data.get("timestamp"),
            message_id=data.get("message_id")
        )
