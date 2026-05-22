# MIM 开发手册 (Development Guide)

## 1. 测试指南

### 运行 E2E 冲突测试
MIM 使用基于多进程模拟的集群测试框架：

```bash
# 安装测试依赖
pip install pytest requests

# 运行冲突矩阵测试
pytest tests/e2e_conflict_matrix.py -v
```

测试包含以下场景：
- **Delete-Wins**: 验证删除证书在并发冲突中的绝对优先级。
- **Epoch Gate**: 验证时钟回流攻击防御。
- **Convergent State**: 验证 A/B/C 三节点同步后的状态最终一致性。

---

## 2. 调试工具 (Visual Debugger)

MIM 提供了一个实时的可视化调试看板，用于生产环境或开发过程中的状态监控。

1. **启动服务器**: `uvicorn api.server:app --port 8000`
2. **访问看板**: 在浏览器打开 `http://localhost:8000/debug`
3. **监控重点**:
   - **Version Vector Diff**: 查看不同节点间的同步延迟。
   - **Conflict Hotspots**: 观察哪些 Actor 频繁触发 LWW 冲突解决。
   - **Cache Status**: 实时查看 `InsightTTLCache` 的内存占用与过期情况。

---

## 3. 扩展三元组提取策略

MIM 支持两种级别的提取策略扩展：

### A. 基于正则的启发式扩展 (MockExtractor)
在 `runtime/extractor.py` 中修改 `MockExtractor`：
1. 在 `extract_memories` 方法中添加新的正则表达式。
2. 定义提取后的 `MemoryOperation`。
3. 示例：
   ```python
   # 识别 "X depends on Y"
   dep_match = re.search(r"([\w-]+) depends on ([\w-]+)", text, re.I)
   if dep_match:
       ops.append(MemoryOperation(..., links=[{"to_id": obj, "type": "DEPENDS_ON"}]))
   ```

### B. 基于本地 LLM 的 Prompt 扩展 (GemmaExtractor)
在 `runtime/llm_extractor.py` 中修改：
1. 更新 `triple_prompt` 增加更多的 Context 信息或 Few-shot 示例。
2. 在 `Step 2: 逐句提取三元组` 中调整 JSON 解析逻辑，支持更复杂的关系类型。

---

## 4. 性能调优

- **异步预计算**: 核心逻辑位于 `runtime/runtime.py` 的 `_async_precompute`。
- **缓存配置**: 在 `runtime/cache.py` 中调整 `default_ttl_sec`。
- **GC 周期**: 修改 `runtime/runtime.py` 中的 `maintain` 调用频率。
