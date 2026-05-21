import httpx

class MimClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    async def health(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/health")
            return resp.json()

    async def remember(self, user_id, content, memory_type="project", tag="mim"):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/remember",
                json={"user_id": user_id, "content": content, "memory_type": memory_type, "tag": tag}
            )
            return resp.json()

    async def recall(self, user_id, tag=None):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/recall",
                json={"user_id": user_id, "tag": tag}
            )
            return resp.json()

    async def search(self, user_id, query):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/search",
                json={"user_id": user_id, "query": query}
            )
            return resp.json()

    async def forget(self, memory_id):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/forget",
                json={"memory_id": memory_id}
            )
            return resp.json()

    async def ingest(self, user_id, text):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/ingest",
                json={"user_id": user_id, "text": text}
            )
            return resp.json()

    async def sync(self, source_path):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/sync",
                json={"source_path": source_path}
            )
            return resp.json()
