import hashlib
import random
import math
import httpx

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

class OllamaEmbeddingProvider:
    def __init__(self, model="nomic-embed-text", base_url="http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def get_embedding(self, text):
        try:
            with httpx.Client() as client:
                resp = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=30.0
                )
                resp.raise_for_status()
                return resp.json()["embedding"]
        except Exception as e:
            print(f"[Ollama] Error fetching embedding: {e}")
            # Fallback to a zero vector or mock if preferred.
            # For now, we return a zero vector of appropriate size (nomic is 768)
            return [0.0] * 768

def cosine_similarity(v1, v2):
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a*b for a, b in zip(v1, v2))
    # 假设输入已归一化，否则需要除以模长乘积
    return dot
