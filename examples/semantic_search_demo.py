import os
import shutil
import subprocess

def run_cli(args):
    cmd = ["python", "cli.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

def main():
    print("--- MIM P7 Semantic Search Demo ---")
    if os.path.exists("mim/snapshots"):
        shutil.rmtree("mim/snapshots")

    # 1. 记录一些不同主题的记忆
    print("\n[1] Adding memories with different themes...")
    run_cli(["remember", "u1", "Learning Python programming and data science", "education", "python"])
    run_cli(["remember", "u1", "Developing a JavaScript React frontend", "work", "js"])
    run_cli(["remember", "u1", "Gardening tips for planting spring flowers", "hobby", "garden"])
    run_cli(["remember", "u1", "How to bake a chocolate cake", "hobby", "cooking"])

    # 2. 关键词搜索 (recall)
    print("\n[2] Recall by tag 'python' (Exact match):")
    print(run_cli(["recall", "u1", "python"]))

    # 3. 语义搜索 (search) - 搜索 "coding"
    print("\n[3] Semantic search for 'coding' (Should find Python and JS):")
    print(run_cli(["search", "u1", "coding"]))

    # 4. 语义搜索 (search) - 搜索 "food"
    print("\n[4] Semantic search for 'food' (Should find cake/cooking):")
    print(run_cli(["search", "u1", "food"]))

    # 5. 语义搜索 (search) - 搜索 "plants"
    print("\n[5] Semantic search for 'plants' (Should find garden):")
    print(run_cli(["search", "u1", "plants"]))

    print("\n--- Demo Completed ---")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
