import sys
import json
import os

# 确保 mim 路径在 sys.path 中
mim_path = "C:/Users/rachel/mim"
if mim_path not in sys.path:
    sys.path.insert(0, mim_path)

try:
    from runtime.core import mems, index, runtime, restore_all, index_store
    from runtime.extractor import DialogueMessage, MockExtractor
except Exception as e:
    # 彻底吞掉导入阶段的错误，防止 hook 报错
    sys.exit(0)

def main():
    # 从 stdin 读取 Claude Code 传来的 JSON
    try:
        # 增加超时处理或非阻塞读取，防止 stdin 导致挂起
        input_data = json.load(sys.stdin)
        prompt = input_data.get("prompt", "")
    except Exception:
        sys.exit(0)

    if not prompt:
        sys.exit(0)

    # 初始化并恢复状态
    try:
        restore_all()
    except Exception:
        sys.exit(0)

    # 模拟提取对话记忆
    try:
        user_id = "rachel"
        extractor = MockExtractor()
        messages = [DialogueMessage(role="user", content=prompt)]

        extracted = runtime.ingest_dialogue(user_id, messages, extractor)

        if extracted:
            for mem in extracted:
                mems[mem.id] = mem
            index_store.save(index)
            # 只有成功提取到记忆时才输出 JSON 消息，否则完全静默
            print(json.dumps({"systemMessage": f"已自动提取并保存 {len(extracted)} 条记忆。"}))
    except Exception:
        pass

    sys.exit(0)

if __name__ == "__main__":
    main()
