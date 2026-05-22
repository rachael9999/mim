import re
from typing import List
from runtime.actor import MemoryActor

def calculate_jaccard_similarity(text1: str, text2: str) -> float:
    """计算简单的 Jaccard 相似度"""
    def tokenize(text):
        return set(re.findall(r'\w+', text.lower()))

    words1 = tokenize(text1)
    words2 = tokenize(text2)

    if not words1 or not words2:
        return 0.0

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    return len(intersection) / len(union)

def find_duplicate(user_id: str, new_content: str, existing_mems: dict, threshold: float = 0.85) -> str:
    """在现有记忆中查找重复内容，返回重复的 Actor ID"""
    for mid, actor in existing_mems.items():
        if actor.owner_id == user_id and not actor._deleted:
            sim = calculate_jaccard_similarity(new_content, actor.content.value)
            if sim >= threshold:
                return mid
    return None

def reinforce_memory(runtime, actor, reason: str = "Duplicate reinforcement"):
    """强化现有记忆 (例如增加重要性或更新最后访问时间)"""
    from runtime.core import NODE_ID
    import time
    runtime.dispatch(actor, "update_importance", {"importance": min(actor.importance.value + 0.1, 2.0)})
    runtime.dispatch(actor, "touch", {"timestamp": time.time()})
    print(f"[DEDUP] Reinforced memory {actor.id}: {reason}")
