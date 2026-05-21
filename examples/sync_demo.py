import os
import shutil
import subprocess
import json

def run_node_cli(node_dir, args):
    # 模拟在不同目录下运行 CLI
    env = os.environ.copy()
    # cli.py 中使用了硬编码的 mim/snapshots，我们需要通过修改 SNAPSHOT_DIR 来模拟多节点
    # 简单的做法是临时修改 cli.py 的内容，或者让 cli.py 接受环境参数
    # 这里我们采用更简单的：手动创建两个目录并复制 cli.py 进去执行
    os.makedirs(node_dir, exist_ok=True)
    if not os.path.exists(os.path.join(node_dir, "cli.py")):
        # 复制整个项目结构到节点目录 (简化处理)
        for item in ["cli.py", "runtime", "crdt"]:
            src = item
            dst = os.path.join(node_dir, item)
            if os.path.isdir(src):
                if os.path.exists(dst): shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    cmd = ["python", "cli.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=node_dir)
    return result.stdout.strip()

def main():
    print("--- MIM P6 Distributed Sync Demo ---")
    node_a = "demo_node_a"
    node_b = "demo_node_b"

    # 清理
    for d in [node_a, node_b]:
        if os.path.exists(d): shutil.rmtree(d)

    # 1. Node A 创建记忆
    print("\n[1] Node A: Creating memory...")
    run_node_cli(node_a, ["remember", "u1", "Node A Content", "project", "tagA"])

    # 获取 ID
    mids = [f[:-5] for f in os.listdir(os.path.join(node_a, "mim/snapshots")) if f.startswith("mem_")]
    mid = mids[0]

    # 2. Node B 创建并发更新
    print(f"\n[2] Node B: Syncing from A and adding concurrent tag...")
    run_node_cli(node_b, ["sync", os.path.join(os.getcwd(), node_a, "mim/snapshots")])

    # 验证 mid
    mids_b = [f[:-5] for f in os.listdir(os.path.join(node_b, "mim/snapshots")) if f.startswith("mem_")]
    mid_b = mids_b[0]

    # 模拟 Node B 对同一个 mid 进行修改：
    path_b = os.path.join(node_b, "mim/snapshots", f"{mid_b}.json")
    with open(path_b, "r") as f: data = json.load(f)
    data["tags"]["adds"]["tagB"] = ["nodeB:100"] # 模拟 node B 的并发 tag
    with open(path_b, "w") as f: json.dump(data, f)

    # 3. Node A 逻辑删除
    print(f"\n[3] Node A: Forgetting {mid_b}...")
    run_node_cli(node_a, ["forget", mid_b])

    # 4. Node B 同步 (现在 Node B 会合并 Node A 的证书)
    print("\n[4] Node B: Syncing from Node A (should detect Delete Certificate)...")
    run_node_cli(node_b, ["sync", os.path.join(os.getcwd(), node_a, "mim/snapshots")])

    # 5. 验证结果
    print("\n[5] Node B: Recalling...")
    output = run_node_cli(node_b, ["recall", "u1"])
    print(f"Output: {output}")

    if "No memories found" in output:
        print("\n[OK] SUCCESS: Delete Certificate correctly prevented resurrection on Node B.")
    else:
        print("\n[FAIL] FAILURE: Memory still visible on Node B.")

if __name__ == "__main__":
    main()
