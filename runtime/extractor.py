import re
import hashlib
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
        return ops
