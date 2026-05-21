class LWWRegister:
    def __init__(self, value=None, clock=0, node_id="local"):
        self.value = value
        self.clock = clock
        self.node_id = node_id

    def set(self, value, clock, node_id="local"):
        # 使用 (lamport, node_id) 二元组作为排序依据，确保确定性
        if (clock, node_id) >= (self.clock, self.node_id):
            self.value = value
            self.clock = clock
            self.node_id = node_id

    def merge(self, other_dict):
        # other_dict: {"value": ..., "clock": ..., "node_id": ...}
        remote_clock = other_dict.get("clock", 0)
        remote_node = other_dict.get("node_id", "unknown")

        if (remote_clock, remote_node) > (self.clock, self.node_id):
            self.value = other_dict.get("value")
            self.clock = remote_clock
            self.node_id = remote_node

    def to_dict(self):
        return {
            "value": self.value,
            "clock": self.clock,
            "node_id": self.node_id
        }
