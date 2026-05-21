import os, json

class SnapshotStore:
    def __init__(self, dir):
        self.dir = dir
        os.makedirs(dir, exist_ok=True)

    def save(self, mem_actor):
        temp_path = f"{self.dir}/{mem_actor.id}.json.tmp"
        final_path = f"{self.dir}/{mem_actor.id}.json"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(mem_actor.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(temp_path, final_path)

    def load(self, id):
        path = f"{self.dir}/{id}.json"
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
