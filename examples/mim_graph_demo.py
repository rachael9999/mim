import os
import shutil
import subprocess
import time

def run_cli(args):
    cmd = ["python", "cli.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())

def main():
    print("--- MIM P11-P14 MIM-Graph (Spreading Activation) Demo ---")

    # 1. 准备环境
    if os.path.exists("mim/snapshots"):
        shutil.rmtree("mim/snapshots")
    os.makedirs("mim/snapshots", exist_ok=True)

    # 2. 构建知识图谱 (使用特定 ID 模式进行可预测的链接)
    print("\n[1] Building Knowledge Graph with explicit IDs...")
    # 我们使用 tag:id 语法在 cli.py 中注入固定 ID
    run_cli(["remember", "u1", "Tesla Corporation", "entity", "p14:tesla_node"])
    run_cli(["remember", "u1", "Electric Vehicles", "entity", "p14:ev_node"])
    run_cli(["remember", "u1", "CO2 Emissions", "entity", "p14:emissions_node"])
    run_cli(["remember", "u1", "Global Climate Change", "entity", "p14:climate_node"])

    # 3. 建立多级链接 (Link Actors)
    print("\n[2] Linking Nodes...")
    # Tesla (A) -> EV (B) -> Emissions (C) -> Climate Change (D)
    run_cli(["link", "tesla_node", "ev_node", "Produces", "1.0"])
    run_cli(["link", "ev_node", "emissions_node", "Reduces", "0.9"])
    run_cli(["link", "emissions_node", "climate_node", "Influences", "1.0"])

    # 4. Spreading Activation 查询
    print("\n[3] Performing Spreading Activation Query for 'Tesla impact'...")
    # 查询 Tesla，预期能量会扩散到 climate_node (3 跳外)
    run_cli(["graph_query", "u1", "Tesla impact"])

    # 5. 测试文件夹导入 (自动层级链接)
    print("\n[4] Testing Folder Ingestion (Auto-linking)...")
    test_dir = "mim/test_knowledge_base"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)
    with open(os.path.join(test_dir, "policy.md"), "w") as f:
        f.write("New energy policy favors sustainable transport.")
    with open(os.path.join(test_dir, "battery.txt"), "w") as f:
        f.write("Lithium batteries are key for sustainable transport.")

    run_cli(["ingest_folder", "u1", test_dir])

    # 6. 图谱查询文件夹内容
    print("\n[5] Graph query for 'sustainable transport' (Should find policy and battery via folder link):")
    run_cli(["graph_query", "u1", "sustainable transport"])

    print("\n--- Demo Completed ---")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
