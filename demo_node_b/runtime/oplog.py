import os
import json
from runtime.message import Message

class Oplog:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def append(self, message):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(message.to_dict(), ensure_ascii=False) + "\n")

    def read_all(self):
        if not os.path.exists(self.path):
            return []
        messages = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    messages.append(Message.from_dict(json.loads(line)))
        return messages

    def truncate(self):
        if os.path.exists(self.path):
            os.remove(self.path)
