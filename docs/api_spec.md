# MIM API 规范 (API Specification)

本文档详细说明了 MIM HTTP API 的端点、输入输出格式及错误处理。

## 基础信息
- **Base URL**: `http://localhost:8000` (默认)
- **Content-Type**: `application/json`

---

## 1. 核心同步接口

### `POST /v1/pull`
根据客户端版本向量增量拉取 Actor 状态。

**输入 (`PullRequest`):**
```json
{
  "user_id": "rachel",
  "vector": {
    "node_a": 1024,
    "node_b": 512
  }
}
```

**输出:**
- `updates`: 发生变更的 Actor 状态列表。
- `certs`: 当前节点的所有删除证书。
- `current_vector`: 节点当前的全局向量。

---

### `POST /v1/sync_certs`
批量合并删除证书。

**输入:** `Dict[scope, Certificate]`

**输出:** `{"status": "certs_merged", "count": N}`

---

### `POST /v1/sync_single`
接收单个 Actor 的主动推送。

**输入:** `ActorStateDict` (包含 CRDT 内部字段)

**输出:** `{"status": "merged", "id": "..."}`

---

## 2. 记忆操作接口

### `POST /v1/remember`
存储原始记忆片段。

**输入:**
```json
{
  "user_id": "string",
  "content": "string",
  "memory_type": "project|task|fact",
  "tag": "string"
}
```

---

### `POST /v1/ingest`
触发智能化提取流程（调用本地 LLM）。

**输入:**
```json
{
  "user_id": "rachel",
  "text": "对话内容或文档片段"
}
```

---

## 3. 搜索与推理接口

### `POST /v1/graph_query`
执行基于能量扩散的图搜索。

**输入:**
```json
{
  "user_id": "rachel",
  "query": "搜索关键词",
  "max_hops": 3
}
```

**输出:**
- `results`: 包含 `score`, `content` 和 `explanation` (推理路径)。

---

### `POST /v1/discover` (P19)
自动聚类并生成 Insights。支持多层缓存。

**输入参数:**
- `user_id`: 用户 ID
- `top_n`: 返回 Insight 的数量
- `force_refresh`: 是否强制跳过缓存重新计算

---

## 4. 生产调试与运维

### `GET /v1/debug/runtime_state` (P16)
导出当前节点的完整运行时快照，用于 Visual Debugger。

**输出:**
- `node_id`: 当前节点 ID
- `actors`: 所有 Actor 的时钟、向量与内容预览
- `certificates`: 证书列表
- `cache_stats`: 缓存命中率与生存状态

---

### `GET /metrics`
Prometheus 风格的运行指标。

**核心指标:**
- `requests_total`: 总请求数
- `conflicts_detected`: CRDT 冲突（被 LWW 解决）的次数
- `certs_hit`: 被可见性过滤拦截的次数
- `cache_stats`: 缓存性能指标

---

## 5. 错误码规范

| HTTP 状态码 | 错误代码 (code) | 描述 |
| :--- | :--- | :--- |
| 404 | `NOT_FOUND` | 找不到指定的 Actor |
| 410 | `ALREADY_FORGOTTEN` | 该记忆已被删除证书覆盖，无法访问 |
| 500 | `INGEST_ERROR` | LLM 提取管道异常 |
| 500 | `SYNC_ERROR` | 节点同步握手失败 |
| 500 | `INTERNAL_ERROR` | 系统内部未知异常 |
