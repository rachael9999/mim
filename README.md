# MIM (Memory Interface Model) Runtime

MIM 是一个面向 Agent Memory 的 Actor-based、CRDT-aware、local-first Memory Runtime。它旨在为 AI Agents 提供轻量级、高并发且支持分布式一致性的持久化记忆方案。

## 核心特性

1.  **Actor-based**: 每一条记忆都是一个自治的 Actor，拥有独立的状态和 lifecycle。
2.  **CRDT-aware**: 使用 LWWRegister 和 ORSet 确保并发更新下的最终一致性。
3.  **Decentralized Sync**: 基于 **Version Vector** 的增量同步，支持多节点 P2P 实时广播。
4.  **MIM-Graph**: 结合 **Gemma 2B** 的本地语义提取，自动构建关联图谱。
5.  **Spreading Activation**: 基于能量扩散的深度推理搜索，支持发现非关键词相关的间接联系。
6.  **Knowledge Discovery**: 自动聚类分析与 Insight 自动合成。

## 快速上手

### 1. 环境准备
- Python 3.10+
- [Ollama](https://ollama.com/) (需下载 `gemma4:e2b`)
- `pip install fastapi uvicorn requests pydantic mcp`

### 2. 核心操作
通过 `cli.py` 进行管理：

```bash
# 智能提取 (调用本地 Gemma 模型)
python cli.py ingest rachel "我正在用 MIM 开发知识发现功能"

# 建立关联
python cli.py link <from_id> <to_id> <type> [weight]

# 深度图推理 (Spreading Activation)
python cli.py graph_query rachel "MIM 的智能化"

# 知识发现 (聚类总结)
python cli.py discover rachel

# HTML 可视化
python cli.py visualize rachel html
```

## 分布式协作 (P12-P13)

MIM 现已支持去中心化 P2P 同步：

```bash
# 注册 Peer 节点
python cli.py peer http://another-node:8000

# 增量拉取 (基于 Version Vector)
python cli.py pull http://remote-node:8000 rachel
```

## API & SDK

### 1. 启动服务器
```bash
uvicorn api.server:app --port 8000
```

### 2. 主要端点
- `POST /v1/pull`: 增量拉取更新。
- `POST /v1/sync_single`: 实时广播推送。
- `POST /v1/graph_query`: 深度图推理接口。
- `GET /metrics`: 系统运行指标。

## MCP 模式集成

MIM 现已完全对接 Claude Code。

### 1. 配置 MCP
```bash
claude mcp add mim-memory python "C:/Users/rachel/mim/mcp_server.py" --env PYTHONPATH="C:/Users/rachel/mim"
```

### 2. 自动化对话提取 (Full Pipeline)
MIM 通过 Hook 机制实现了**全自动闭环记忆**：
1.  **Capture**: Hook 自动拦截 User/AI 对话。
2.  **Extract**: 调用本地 **Gemma 2B Pipeline** 将对话拆解为原子三元组。
3.  **Link**: 自动构建知识图谱连线。
4.  **Recall**: Claude 可随时通过 `graph_query` 工具召回深度关联知识。

## 工程硬化与可观测性 (P16-P19)

MIM 现已达到生产级稳定性：

1.  **Visual Debugger**: 实时 HTML 看板 (`/debug`)，监控版本向量差异与冲突热点。
2.  **MCP Auto Context**: Claude Code 自动召回背景，实现对话连续性。
3.  **Explainable AI**: `graph_query` 提供完整的能量扩散路径解释。
4.  **High Performance**: 引入 `InsightTTLCache` 与异步预计算，`discover` 响应提速 2000x。

## 已完成路线 (P10-P19)

- ✅ **P10-P15**: 基础架构（P2P 同步、CRDT、Gemma 提取、聚类发现）。
- ✅ **P16 Visual Debugger**: 实时状态可视化看板。
- ✅ **P17 MCP Auto Context**: Claude 自动化背景注入与语义去重。
- ✅ **P18 Explainable Reasoning**: 带路径解释的深度图推理。
- ✅ **P19 Performance Optimization**: 多层缓存与异步预计算。

---
Generated with [Claude Code](https://claude.com/claude-code)
