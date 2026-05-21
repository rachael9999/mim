import requests
import json
import re
from typing import List
from runtime.extractor import DialogueMessage, MemoryOperation

class GemmaExtractor:
    def __init__(self, model="gemma2:2b", base_url="http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def summarize_cluster(self, memories: List[str]) -> str:
        """为一组记忆生成摘要"""
        text = "\n".join([f"- {m}" for m in memories])
        prompt = f"""
Summarize the following related memories into a single concise insight or fact.
Be specific and preserve technical details.

Memories:
{text}

Summary Insight:
"""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=60
            )
            if response.status_code == 200:
                return response.json().get("response", "").strip()
        except Exception as e:
            print(f"[GemmaExtractor] Summarization error: {e}")
        return ""

    def extract_memories(self, messages: List[DialogueMessage]) -> List[MemoryOperation]:
        combined_text = "\n".join([f"{m.role}: {m.content}" for m in messages])

        # Step 1: 句子拆分 (Decomposition)
        split_prompt = """
Break down the following dialogue into multiple simple, independent atomic facts or technical statements.
Each line should be a single statement. Do not add any preamble.

Dialogue:
""" + combined_text + """

Atomic Statements:
"""

        try:
            split_response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": split_prompt,
                    "stream": False,
                    "options": {"temperature": 0.1}
                },
                timeout=60
            )

            statements = []
            if split_response.status_code == 200:
                raw_split = split_response.json().get("response", "")
                statements = [s.strip() for s in raw_split.split("\n") if len(s.strip()) > 5]
                print(f"[GemmaExtractor] Split into {len(statements)} statements.")

            if not statements:
                statements = [combined_text]

            # Step 2: 逐句提取三元组
            all_ops = []
            for stmt in statements:
                triple_prompt = """
Extract a single knowledge graph triple (Subject, Predicate, Object) from this statement.
Format: {"subj": "...", "rel": "...", "obj": "...", "type": "..."}
Statement: """ + stmt + """

JSON Output:
"""
                triple_response = requests.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": triple_prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.1}
                    },
                    timeout=30
                )

                if triple_response.status_code == 200:
                    raw_content = triple_response.json().get("response", "{}")
                    try:
                        item = json.loads(raw_content)
                        if isinstance(item, dict) and "subj" in item:
                            subj = item.get('subj', 'unknown')
                            rel = item.get('rel', 'RELATED_TO')
                            obj = item.get('obj', 'unknown')
                            mem_type = item.get('type', 'fact')

                            content = f"{subj} {rel} {obj}"
                            all_ops.append(MemoryOperation(
                                content=content,
                                memory_type=mem_type,
                                tags=["llm_extracted", self.model, "pipeline_v2"],
                                links=[{"to_id": str(obj).lower().replace(" ", "_"), "type": rel}]
                            ))
                            print(f"[GemmaExtractor] Extracted Triple: {content}")
                    except:
                        continue
            return all_ops

        except Exception as e:
            print(f"[GemmaExtractor] Pipeline Error: {e}")
            return []
