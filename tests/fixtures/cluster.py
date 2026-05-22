import requests
import json
import time
import subprocess
import os
import shutil
import signal

class ClusterFixture:
    """管理 A/B/C 三个模拟节点的启停与状态"""
    def __init__(self, base_port=8000, root_dir="tests/data"):
        self.base_port = base_port
        self.root_dir = os.path.abspath(root_dir)
        self.nodes = {
            "A": f"http://localhost:{base_port}",
            "B": f"http://localhost:{base_port+1}",
            "C": f"http://localhost:{base_port+2}"
        }
        self.processes = {}
        self.node_dirs = {}

        if os.path.exists(self.root_dir):
            shutil.rmtree(self.root_dir)
        os.makedirs(self.root_dir)

    def start_node(self, name):
        port = self.base_port + (ord(name) - ord('A'))
        node_dir = os.path.join(self.root_dir, name)
        os.makedirs(node_dir, exist_ok=True)
        self.node_dirs[name] = node_dir

        env = os.environ.copy()
        env["SNAPSHOT_DIR"] = node_dir
        env["NODE_ID"] = name
        env["PYTHONPATH"] = os.getcwd()

        # 使用 subprocess.DEVNULL 避免管道阻塞
        proc = subprocess.Popen(
            ["uvicorn", "api.server:app", "--port", str(port), "--host", "127.0.0.1"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.processes[name] = proc

        # Wait for healthy
        timeout = 15
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = requests.get(f"{self.nodes[name]}/health", timeout=1)
                if resp.status_code == 200:
                    return
            except:
                time.sleep(0.5)

        # 如果启动失败，尝试获取一些错误信息
        raise RuntimeError(f"Node {name} failed to start at {self.nodes[name]}")

    def stop_node(self, name):
        if name in self.processes:
            proc = self.processes[name]
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            del self.processes[name]

    def stop_all(self):
        for name in list(self.processes.keys()):
            self.stop_node(name)

    def remember(self, node, user, content, mtype="fact", tag="mim"):
        resp = requests.post(f"{self.nodes[node]}/v1/remember", json={
            "user_id": user, "content": content, "memory_type": mtype, "tag": tag
        })
        resp.raise_for_status()
        return resp.json()["id"]

    def forget(self, node, mem_id):
        return requests.post(f"{self.nodes[node]}/v1/forget", json={"memory_id": mem_id})

    def recall(self, node, user, tag=None):
        return requests.post(f"{self.nodes[node]}/v1/recall", json={"user_id": user, "tag": tag}).json()

    def sync_pair(self, from_node, to_node, user_id):
        """让 to_node 从 from_node 同步数据 (模拟 pull)"""
        from_url = self.nodes[from_node]
        to_url = self.nodes[to_node]

        # 1. 获取增量更新
        pull_resp = requests.post(f"{from_url}/v1/pull", json={
            "user_id": user_id,
            "vector": {}
        })
        pull_data = pull_resp.json()

        # 2. 同步 Actor 状态
        for update in pull_data["updates"]:
            requests.post(f"{to_url}/v1/sync_single", json=update)

        # 3. 同步证书 (关键点：解决 Delete-Wins)
        requests.post(f"{to_url}/v1/sync_certs", json=pull_data["certs"])

    def sync_all(self, user_id):
        """全集群全量同步 (多次迭代确保收敛)"""
        nodes = list(self.nodes.keys())
        for _ in range(2): # 两次迭代确保 A->B->C 这种传递性同步完成
            for i in range(len(nodes)):
                for j in range(len(nodes)):
                    if i != j:
                        self.sync_pair(nodes[i], nodes[j], user_id)
