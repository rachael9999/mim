import re
import hashlib
import os
from typing import List, Optional
from dataclasses import dataclass, field

@dataclass
class DialogueMessage:
    role: str
    content: str
    message_id: Optional[str] = None

    def __post_init__(self):
        if self.message_id is None:
            # 如果没有提供 ID，基于内容生成确定性 ID 用于去重测试
            self.message_id = hashlib.md5(self.content.encode()).hexdigest()

@dataclass
class MemoryOperation:
    content: str
    memory_type: str = "fact"
    tags: List[str] = field(default_factory=list)
    links: List[dict] = field(default_factory=list) # {"to_id": ..., "type": ..., "weight": ...}

class MockExtractor:
    def extract_memories(self, messages: List[DialogueMessage]) -> List[MemoryOperation]:
        ops = []
        for msg in messages:
            text = msg.content

            # 启发式 1: "working on [X] project"
            project_match = re.search(r"working on (?:the )?([\w-]+) project", text, re.I)
            if project_match:
                project_name = project_match.group(1)
                ops.append(MemoryOperation(
                    content=f"User is working on {project_name} project",
                    memory_type="project",
                    tags=[project_name.lower(), "extracted"]
                ))

            # 启发式 2: "remind me to [Y]"
            task_match = re.search(r"remind me to (.+)", text, re.I)
            if task_match:
                task_content = task_match.group(1).strip()
                ops.append(MemoryOperation(
                    content=task_content,
                    memory_type="task",
                    tags=["todo", "extracted"]
                ))

            # 启发式 3: "remember that [Z]"
            fact_match = re.search(r"remember that (.+)", text, re.I)
            if fact_match:
                fact_content = fact_match.group(1).strip()
                ops.append(MemoryOperation(
                    content=fact_content,
                    memory_type="fact",
                    tags=["extracted"]
                ))

            # 启发式 4: "A is related to B" (简单的实体链接模式)
            rel_match = re.search(r"([\w-]+) is (?:related to|part of|dependent on|member of) ([\w-]+)", text, re.I)
            if rel_match:
                subj, obj = rel_match.group(1).lower(), rel_match.group(2).lower()
                # 尝试查找已存在的节点，或者记录为待链接
                ops.append(MemoryOperation(
                    content=f"{subj} has relation with {obj}",
                    memory_type="relation",
                    tags=["link", "extracted"],
                    links=[{"to_id": obj, "type": "RelatedTo", "weight": 0.8}]
                ))

            # 启发式 6: 关键词识别 (MIM, MCP, P11, etc.)
            for kw in ["MIM", "MCP", "P11", "Graph", "Spreading"]:
                if kw.lower() in text.lower():
                    ops.append(MemoryOperation(
                        content=text,
                        memory_type="chat_context",
                        tags=[kw.lower(), "chat"],
                        links=[{"to_id": kw.lower() + "_concept", "type": "mentions", "weight": 0.5}]
                    ))
        return ops

class FolderCrawler:
    def __init__(self, runtime):
        self.runtime = runtime

    def crawl(self, user_id, root_path):
        """扫描文件夹并提取知识，构建层级图谱"""
        if not os.path.exists(root_path):
            print(f"[Crawler] Path not found: {root_path}")
            return []

        results = []
        path_to_id = {} # 路径到 ID 的映射，用于构建层级链接

        # 1. 首先确保根目录节点存在
        root_abs = os.path.abspath(root_path)
        root_id = f"dir_{hashlib.md5(root_abs.encode()).hexdigest()[:10]}"
        root_mem = self.runtime.create_actor_if_not_exists(
            root_id, user_id, f"Directory: {os.path.basename(root_abs)}", "directory"
        )
        self.runtime.dispatch(root_mem, "add_tag", {"tag": "root_dir"})
        path_to_id[root_abs] = root_id
        results.append(root_mem)

        # 2. 递归遍历
        for root, dirs, files in os.walk(root_abs):
            current_dir_abs = os.path.abspath(root)
            current_dir_id = path_to_id.get(current_dir_abs)

            # 如果当前目录不在映射中（子目录），创建它
            if not current_dir_id:
                current_dir_id = f"dir_{hashlib.md5(current_dir_abs.encode()).hexdigest()[:10]}"
                current_dir_mem = self.runtime.create_actor_if_not_exists(
                    current_dir_id, user_id, f"Directory: {os.path.basename(current_dir_abs)}", "directory"
                )
                path_to_id[current_dir_abs] = current_dir_id
                results.append(current_dir_mem)

                # 建立与父目录的层级链接
                parent_dir_abs = os.path.dirname(current_dir_abs)
                if parent_dir_abs in path_to_id:
                    self.runtime.dispatch(current_dir_mem, "add_link", {
                        "to_id": path_to_id[parent_dir_abs],
                        "type": "parent_of",
                        "weight": 1.0
                    })
                    # 双向链接提高搜索能效
                    parent_mem = self.runtime.mems.get(path_to_id[parent_dir_abs])
                    if parent_mem:
                        self.runtime.dispatch(parent_mem, "add_link", {
                            "to_id": current_dir_id,
                            "type": "contains",
                            "weight": 0.5
                        })

            # 3. 处理文件
            for filename in files:
                if filename.endswith((".txt", ".md", ".py", ".js", ".json", ".go")):
                    file_path = os.path.join(root, filename)
                    file_abs = os.path.abspath(file_path)

                    try:
                        with open(file_abs, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                    except Exception as e:
                        print(f"[Crawler] Error reading {file_path}: {e}")
                        continue

                    file_id = f"file_{hashlib.md5(file_abs.encode()).hexdigest()[:10]}"
                    file_mem = self.runtime.create_actor_if_not_exists(
                        file_id, user_id, f"File: {filename}", "file"
                    )

                    # 限制快照长度，避免 Actor 臃肿
                    self.runtime.dispatch(file_mem, "update_content", {"content": content[:2000]})

                    # 建立与当前目录的层级链接
                    self.runtime.dispatch(file_mem, "add_link", {
                        "to_id": current_dir_id,
                        "type": "contained_in",
                        "weight": 1.0
                    })

                    # 简单的代码实体提取 (例如 Python import)
                    if filename.endswith(".py"):
                        imports = re.findall(r"^import (\w+)|^from (\w+)", content, re.M)
                        for imp in imports:
                            lib_name = imp[0] or imp[1]
                            self.runtime.dispatch(file_mem, "add_tag", {"tag": f"use:{lib_name}"})

                    results.append(file_mem)

        return results
