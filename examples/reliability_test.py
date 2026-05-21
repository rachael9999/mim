import os
import json
import shutil
import subprocess
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from runtime.message import Message

def run_cli(args):
    cmd = ["python", "cli.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

def test_atomic_and_recovery():
    print("--- MIM P5 Reliability Test ---")
    if os.path.exists("mim/snapshots"):
        shutil.rmtree("mim/snapshots")

    # 1. 创建一个记忆
    print("\n[1] Creating initial memory...")
    run_cli(["remember", "u1", "Stability is key"])

    # 获取 mem_id
    mids = [f for f in os.listdir("mim/snapshots") if f.startswith("mem_") and f.endswith(".json")]
    mid = mids[0][:-5]

    # 2. 模拟崩溃：手动向 oplog 写入一条未提交的消息
    print(f"\n[2] Simulating crash for {mid}...")
    oplog_path = f"mim/snapshots/oplogs/{mid}.log"
    os.makedirs(os.path.dirname(oplog_path), exist_ok=True)

    # 构造一条更新内容的待恢复消息
    recovery_msg = Message("update_content", {"content": "RECOVERED CONTENT"}, clock=100)
    with open(oplog_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(recovery_msg.to_dict()) + "\n")

    # 3. 运行 recall，触发 restore_all -> recover_actor
    print("\n[3] Running recall (should trigger recovery)...")
    output = run_cli(["recall", "u1"])
    print(output)

    if "RECOVERED CONTENT" in output and "clock:100" in output:
        print("\n[OK] SUCCESS: Recovery triggered and state updated from oplog!")
    else:
        print("\n[FAIL] FAILURE: Recovery failed.")

    # 4. 验证 oplog 已清空
    if not os.path.exists(oplog_path):
        print("[OK] SUCCESS: Oplog truncated after recovery.")
    else:
        print("[FAIL] FAILURE: Oplog still exists.")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    test_atomic_and_recovery()
