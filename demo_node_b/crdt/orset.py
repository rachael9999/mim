class ORSet:
    def __init__(self, init=None):
        self.adds = {v: ["init"] for v in (init or [])}
        self.removes = {}

    def add(self, value, dot):
        # 使用外部注入的 dot (e.g. node_id:clock)
        self.adds.setdefault(value, []).append(dot)

    def remove(self, value, dot):
        if value in self.adds:
            # 记录 remove 记录，包含被覆盖的 dots
            # 简写: 我们将所有现有的 adds 放入 removes
            self.removes.setdefault(value, []).extend(self.adds[value])

    def elements(self):
        # 简化版：只要在 adds 中且不在 removes 中就算存在
        return [v for v in self.adds if set(self.adds[v]) - set(self.removes.get(v, []))]

    def merge(self, other_dict):
        # other_dict: {"adds": {val: [dots]}, "removes": {val: [dots]}}
        remote_adds = other_dict.get("adds", {})
        remote_removes = other_dict.get("removes", {})

        for val, dots in remote_adds.items():
            local_dots = self.adds.setdefault(val, [])
            for dot in dots:
                if dot not in local_dots:
                    local_dots.append(dot)

        for val, dots in remote_removes.items():
            local_dots = self.removes.setdefault(val, [])
            for dot in dots:
                if dot not in local_dots:
                    local_dots.append(dot)

    def to_dict(self):
        return {"adds": self.adds, "removes": self.removes}
