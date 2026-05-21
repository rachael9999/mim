import os
import sys
import subprocess
import time
import asyncio
import shutil

# Ensure project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from api.client import MimClient

async def run_demo():
    print("--- MIM P9 API & SDK Demo ---")

    # 1. 清理并准备环境
    if os.path.exists("mim/snapshots"):
        shutil.rmtree("mim/snapshots")
    os.makedirs("mim/snapshots", exist_ok=True)

    # 2. 启动 FastAPI 服务器
    print("[1] Starting API server...")
    server_process = subprocess.Popen(
        ["uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    client = MimClient("http://127.0.0.1:8000")

    # 等待服务器就绪
    for _ in range(10):
        try:
            res = await client.health()
            if res.get("status") == "ok":
                break
        except:
            pass
        await asyncio.sleep(1)
    else:
        print("Error: Server failed to start.")
        server_process.terminate()
        return

    try:
        # 3. 使用 SDK 记住记忆
        print("[2] Remembering via SDK...")
        await client.remember("alice", "I am testing the new HTTP API", "test", "api")

        # 4. 使用 SDK 摄入对话
        print("[3] Ingesting dialogue via SDK...")
        await client.ingest("alice", "I'm working on the P9 integration today. Remind me to update the docs.")

        # 5. 验证 Recall
        print("[4] Recalling via SDK...")
        memories = await client.recall("alice")
        for m in memories:
            print(f"  - [{m['id']}] {m['content']}")

        # 6. 验证语义搜索
        print("[5] Searching via SDK...")
        results = await client.search("alice", "web interface")
        for r in results:
            print(f"  - [{r['score']:.4f}] {r['content']}")

        # 7. 忘记记忆
        if memories:
            mid = memories[0]['id']
            print(f"[6] Forgetting {mid}...")
            await client.forget(mid)

            print("[7] Recalling again (should have one less)...")
            final_mems = await client.recall("alice")
            print(f"  Count: {len(final_mems)}")

    finally:
        print("[8] Shutting down server...")
        server_process.terminate()
        server_process.wait()
        print("--- Demo Completed ---")

if __name__ == "__main__":
    # 确保在项目根目录运行
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    asyncio.run(run_demo())
