import hashlib
import random
import math

class MockEmbeddingProvider:
    def __init__(self, dimension=32):
        self.dimension = dimension

    def get_embedding(self, text):
        # 确定性 Mock: 基于文本哈希生成随机向量
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        vec = [rng.uniform(-1, 1) for _ in range(self.dimension)]

        # 归一化以方便计算余弦相似度
        norm = math.sqrt(sum(x*x for x in vec))
        return [x/norm for x in vec] if norm > 0 else vec

def cosine_similarity(v1, v2):
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a*b for a, b in zip(v1, v2))
    # 假设输入已归一化，否则需要除以模长乘积
    return dot
