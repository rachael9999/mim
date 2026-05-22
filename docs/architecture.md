# MIM 架构设计 (Architecture)

MIM (Memory Interface Model) 是一个面向 AI Agent 的自治记忆运行时，旨在解决 Agent 记忆的持久化、一致性、可解释性以及大规模关联推理问题。

## 1. 核心模型：Actor-CRDT

MIM 采用 **Actor 模型** 与 **CRDT (Conflict-free Replicated Data Types)** 结合的设计架构：

- **Memory Actor**: 每一条记忆都被建模为一个自治的 Actor。每个 Actor 拥有独立的状态、版本向量（Version Vector）和生命周期。
- **Data-Plane (CRDT)**: 内部状态使用 CRDT 结构（如 `LWWRegister` 存储内容，`ORSet` 存储标签和图关系），确保在任何并发合并场景下都能达成最终一致性，无需中心化锁。
- **Control-Plane (Certificates)**: 引入“删除证书”（Delete Certificates）机制，支持逻辑删除与作用域删除。证书在图中具有 Dominance（支配性），能瞬间使整个子树或特定 Actor 失效，且具备复活防御（Resurrection Defense）能力。

## 2. P2P 广播与同步机制

MIM 支持真正的 Local-first 分布式协作：

- **增量拉取 (Pull)**: 节点间基于 **Version Vector** 对比状态差异，仅传输变更部分，极大地降低了带宽消耗。
- **实时广播 (Push)**: 本地更新通过异步线程即时推送到已注册的 Peer 节点，实现毫秒级的跨节点同步。
- **冲突解决**: 结合 LWW (Last-Write-Wins) 物理时钟与逻辑向量。针对删除操作，采用 **Delete-Wins** 策略，确保删除操作具有最高优先级。

## 3. 多层缓存架构 (P19)

为了支撑复杂的图搜索与 LLM 总结任务，MIM 实现了高性能的三层缓存：

1.  **L1: In-Memory Hot Store**: 运行时的 Actor 对象实例，支持 RLock 保护下的高并发读写。
2.  **L2: InsightTTLCache**: 专门用于存储昂贵的 `discover`（聚类分析）结果。
    - **Key 策略**: 基于 `user_id + graph_version + params`。
    - **失效机制**: 当图谱版本号（Index Version）发生变化时，缓存自动进入校验失效逻辑。
3.  **L3: Disk Persistence**: 所有的 Actor 状态和缓存均支持本地磁盘持久化（JSON + WAL Oplog），支持崩溃后的原子恢复。

## 4. MCP 闭环逻辑 (P17)

MIM 作为 MCP (Model Context Protocol) 服务器与 Claude Code 等 Agent 深度集成：

- **Auto Context**: 在任务开始时，MIM 自动执行语义搜索与图推理，将相关的历史背景注入 Claude 的上下文窗口，实现跨会话的记忆连续性。
- **自动化摄入 (Self-Ingestion)**: 
    - **Capture**: 拦截对话流。
    - **Extract**: 调用本地 **Gemma 2B** Pipeline 进行三元组提取（Subject-Predicate-Object）。
    - **Link**: 自动在图中建立 `mentions`、`related_to` 等关联，完成知识闭环。

## 5. 推理引擎：Spreading Activation (P18)

MIM 不仅仅是存储，更是推理引擎：
- **能量扩散**: 搜索从种子节点（通过语义相似度找回）开始，根据图链接的权重（Weight）和节点的重要性（Importance）向外扩散能量。
- **路径回溯**: 返回结果包含完整的 `explanation`，详细展示了能量是如何通过哪些中间节点传播到最终结果的，实现了“可解释的记忆检索”。
