# MIM Roadmap & Progress

## 阶段 4: 工程硬化与性能巅峰 (当前完成)
### P16 Visual Debugger
- [x] 新增 `GET /v1/debug/runtime_state` 接口。
- [x] 开发 `static/debug_dashboard.html` 实时看板。
- [x] 支持 Version Vector Diff 表格化展示。

### P17 MCP Auto Context & Dedup
- [x] 在 `mcp_server.py` 中集成 `auto_context` 工具。
- [x] 实现 `runtime/dedup.py` 语义去重机制。
- [x] 支持记忆强化 (Reinforcement) 而非重复创建。

### P18 Explainable Reasoning
- [x] 增强 `graph_query` 支持推理路径回溯。
- [x] 在结果中量化展示能量增益 (`energy_gain`)。
- [x] CLI 完美呈现 `Reason: A -> B -> C`。

### P19 Performance & Concurrency
- [x] 实现 `InsightTTLCache` (内存+磁盘)。
- [x] 接入 `IndexActor.version` 实现基于图版本的精准失效。
- [x] 实现异步预计算框架 (`_async_precompute`)。
- [x] 升级全局锁为 `RLock` 并新增 `/v1/discover` 正式接口。

---

## 阶段 5: 深度学习与交互进化 (Next)
### P20 Active Edge Weight Learning
- [ ] 根据 Recall 命中/忽略自动调整边权重。
- [ ] 引入用户反馈闭环。

### P21 Advanced Community Detection
- [ ] 集成 Louvain 或 Girvan-Newman 算法。
- [ ] 在看板中展示多层级社区结构。

### P22 Prometheus & Grafana Integration
- [ ] 标准化 Metrics 格式。
- [ ] 提供预配置的 Grafana Dashboard。
