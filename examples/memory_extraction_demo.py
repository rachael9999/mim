import os
import shutil
import subprocess
import json

def run_cli(args):
    cmd = ["python", "cli.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

def main():
    print("--- MIM P8 Memory Extraction Demo ---")
    if os.path.exists("mim/snapshots"):
        shutil.rmtree("mim/snapshots")

    user = "u1"

    # 1. 模拟第一段对话
    print("\n[1] Ingesting first dialogue...")
    dialogue1 = "Hey, I'm working on the MIM project today. It's really interesting."
    print(run_cli(["ingest", user, dialogue1]))

    # 2. 模拟第二段对话 (包含任务)
    print("\n[2] Ingesting second dialogue...")
    dialogue2 = "Also, remind me to buy coffee later. I'm running low."
    print(run_cli(["ingest", user, dialogue2]))

    # 3. 模拟重复摄入 (测试去重)
    print("\n[3] Ingesting the same dialogue again (should be skipped)...")
    print(run_cli(["ingest", user, dialogue2]))

    # 4. 验证 Recall
    print("\n[4] Recalling memories for u1...")
    print(run_cli(["recall", user]))

    # 5. 验证语义搜索
    print("\n[5] Searching for 'drinks' (Semantic search over extracted memory)...")
    print(run_cli(["search", user, "drinks"]))

    print("\n--- Demo Completed ---")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
