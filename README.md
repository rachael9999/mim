# MIM (Memory Interface Model) Runtime

MIM 是一个面向 Agent Memory 的 Actor-based、CRDT-aware、local-first Memory Runtime。它旨在为 AI Agents 提供轻量级、高并发且支持分布式一致性的持久化记忆方案。

## 核心设计理念

1. **Actor-based**: 每一条记忆都是一个自治的 Actor，拥有独立的状态和 lifecycle。
2. **CRDT-aware**: 使用 LWWRegister (Last-Write-Wins) 和 ORSet (Observed-Remove Set) 确保并发更新下的最终一致性。
3. **Delete Certificate**: 使用对象级/作用域级证书处理删除，防止分布式环境下的“旧数据复活”并支持大规模状态压缩。
4. **Visibility Resolver**: 统一的可见性解析器，实现 recall 过程中的父级/本体删除逻辑过滤。

## 快速上手

### 1. 环境准备
确保已安装 Python 3.x。

### 2. 核心操作
通过 `cli.py` 进行记忆管理：

```bash
# 记录记忆
python cli.py remember <user_id> <content> <type> <tag>
# 示例: python cli.py remember u1 "MIM 是我的项目" project mim

# 回忆查询
python cli.py recall <user_id> [tag]
# 示例: python cli.py recall u1 mim

# 存档记忆 (LWW status 标记)
python cli.py archive <mem_id>

# 忘记记忆 (生成 Actor 级 Delete Certificate)
python cli.py forget <mem_id>

# 删除用户 (生成 User 级 Delete Certificate, 层级覆盖其下所有记忆)
python cli.py delete_user <user_id>
```

## API & SDK (P9)

MIM 现在支持通过 HTTP API 访问，并提供了一个异步 Python SDK。

### 1. 启动 API 服务器
```bash
uvicorn api.server:app --reload
```

### 2. 使用 SDK
```python
from api.client import MimClient
import asyncio

async def main():
    client = MimClient("http://localhost:8000")
    await client.remember("user123", "MIM has an API now!", "feat", "api")
    memories = await client.recall("user123")
    print(memories)

asyncio.run(main())
```

### 3. API 端点
- `POST /v1/remember`: 记录新记忆
- `POST /v1/recall`: 按用户和标签回溯
- `POST /v1/search`: 混合语义搜索
- `POST /v1/ingest`: 提取对话记忆
- `POST /v1/forget`: 逻辑删除记忆
- `POST /v1/sync`: 跨节点状态同步

## 目录结构
```text
mim/
├── api/               # HTTP 接口与 SDK
│   ├── server.py      # FastAPI 服务器
│   └── client.py      # Python SDK (MimClient)
├── crdt/              # CRDT 原始类型 (ORSet, LWWRegister)
├── runtime/           # Runtime 核心逻辑
│   ├── core.py        # 共享初始化逻辑
│   ├── actor.py       # Actor 模型定义
...
```

## 运行演示

MIM 提供了多阶段演示脚本：
- `python examples/remember_recall_demo.py`: 基础 P4 MVP 流程
- `python examples/reliability_test.py`: P5 故障恢复验证
- `python examples/sync_demo.py`: P6 分布式同步与防复活验证
- `python examples/semantic_search_demo.py`: P7 语义搜索验证
- `python examples/memory_extraction_demo.py`: P8 自动记忆提取验证
- `python examples/api_sdk_demo.py`: P9 HTTP API 与 SDK 验证

## 下一步路线 (P5-P9)

- **P5 Runtime Reliability**: 引入 ActorContext 规范化时钟、消息信封与 oplog。
- **P6 CRDT Sync**: 实现 Actor 状态导出/导入与 Stable Watermark GC。
- **P7 Semantic Memory**: 引入 EmbeddingActor 与向量索引支持模糊语义召回。
- **P8 Memory Extractor**: 基于 LLM 的自动记忆提取与实体链接。
- **P9 API/SDK**: 提供标准的 HTTP 接口与多语言 SDK。

---
Generated with [Claude Code](https://claude.com/claude-code)
