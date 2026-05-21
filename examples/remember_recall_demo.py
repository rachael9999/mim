import os
import shutil
import subprocess

def run_cli(args):
    cmd = ["python", "cli.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

def main():
    print("--- MIM P4 Runtime MVP Demo ---")

    # 1. 清理旧环境
    if os.path.exists("mim/snapshots"):
        shutil.rmtree("mim/snapshots")

    # 2. 创建记忆
    print("\n[Step 1] Remembering...")
    print(run_cli(["remember", "u1", "MIM is an AI-Native memory system", "project", "mim"]))
    print(run_cli(["remember", "u1", "I love coding in Python", "personal", "coding"]))
    print(run_cli(["remember", "u2", "This is another user's secret", "private", "hidden"]))

    # 3. 回忆
    print("\n[Step 2] Recalling for u1 with tag 'mim'...")
    print(run_cli(["recall", "u1", "mim"]))

    print("\n[Step 3] Recalling all for u1...")
    print(run_cli(["recall", "u1"]))

    # 4. 存档
    print("\n[Step 4] Archiving a memory...")
    # 获取第一个 mem id
    mids = [f for f in os.listdir("mim/snapshots") if f.startswith("mem_")]
    if mids:
        mid = mids[0][:-5]
        print(run_cli(["archive", mid]))
        print(f"Recalling u1 after archiving {mid}:")
        print(run_cli(["recall", "u1"]))

    # 5. 忘记 (Actor-level Delete Certificate)
    print("\n[Step 5] Forgetting a memory...")
    if len(mids) > 1:
        mid2 = mids[1][:-5]
        print(run_cli(["forget", mid2]))
        print(f"Recalling u1 after forgetting {mid2}:")
        print(run_cli(["recall", "u1"]))

    # 6. 层级删除 (User-level Delete Certificate)
    print("\n[Step 6] Deleting user u2...")
    print(run_cli(["delete_user", "u2"]))
    print("Recalling u2 (should be empty):")
    print(run_cli(["recall", "u2"]))

    print("\n[Step 7] Restart & Persistence Test...")
    # 重新加载 CLI (会调用 restore_all)
    print("Recalling u1 (states should be restored from snapshots):")
    print(run_cli(["recall", "u1"]))

    print("\n--- Demo Completed ---")

if __name__ == "__main__":
    # 确保在 mim 根目录运行
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
