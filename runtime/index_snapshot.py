import os, json

class IndexSnapshotStore:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def save(self, index):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({
                "owner_index": {k: list(v) for k, v in index.owner_index.items()},
                "tag_index": {k: list(v) for k, v in index.tag_index.items()},
                "type_index": {k: list(v) for k, v in index.type_index.items()},
                "vector_store": index.vector_store
            }, f, ensure_ascii=False, indent=2)

    def load(self, index):
        if not os.path.exists(self.path):
            return False
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
            index.owner_index = {k: set(v) for k, v in data["owner_index"].items()}
            index.tag_index = {k: set(v) for k, v in data["tag_index"].items()}
            index.type_index = {k: set(v) for k, v in data["type_index"].items()}
            index.vector_store = data.get("vector_store", {})
        return True
