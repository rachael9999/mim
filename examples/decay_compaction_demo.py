import os
import time
import shutil
import subprocess

def run_cli(args):
    cmd = ["python", "cli.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())

def main():
    print("--- MIM P10 Memory Decay & Compaction Demo ---")

    # 1. 准备环境
    if os.path.exists("mim/snapshots"):
        shutil.rmtree("mim/snapshots")
    os.makedirs("mim/snapshots", exist_ok=True)

    # 2. 记录记忆
    print("\n[1] Creating memories...")
    run_cli(["remember", "u1", "Important project details", "project", "p10"])
    run_cli(["remember", "u1", "Casual coffee chat", "social", "p10"])

    # 3. 初始 Recall
    print("\n[2] Initial Recall (should show 2 active memories):")
    run_cli(["recall", "u1"])

    # 4. 模拟时间流逝 (直接修改快照中的 last_accessed)
    print("\n[3] Simulating time passage (setting last_accessed to 1 day ago)...")
    one_day_ago = time.time() - 86400
    snapshot_dir = "mim/snapshots"
    for fn in os.listdir(snapshot_dir):
        if fn.endswith(".json") and fn.startswith("mem_"):
            path = os.path.join(snapshot_dir, fn)
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["last_accessed"]["value"] = one_day_ago
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)

    # 5. 运行第一次维护 (归档)
    # k=0.0001, 86400s -> exp(-0.0001 * 86400) = exp(-8.64) ≈ 0.00017
    # 这会直接低于 0.1，触发删除。为了演示归档，我们手动调小 k 或者模拟更短的时间。
    # 我们直接运行 maintain，看看它是否变为 archived 或 deleted。
    print("\n[4] Running maintenance (Maintenance Loop)...")
    run_cli(["maintain"])

    # 6. 验证状态
    print("\n[5] Recall after maintenance (should be empty as they decayed below 0.5):")
    run_cli(["recall", "u1"])

    # 7. 检查物理快照确认状态
    print("\n[6] Checking physical snapshots for status:")
    for fn in os.listdir(snapshot_dir):
        if fn.endswith(".json") and fn.startswith("mem_"):
            path = os.path.join(snapshot_dir, fn)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"  Memory {data['id']}: status={data['status']['value']}, importance_calc={data['importance']['value']}")
            if data.get("_deleted"):
                print(f"  - [DELETED] with certificate")

    print("\n--- Demo Completed ---")

if __name__ == "__main__":
    # 确保在项目根目录运行
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
