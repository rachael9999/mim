# MIM Consistency Invariants (一致性不变量)

为了确保 MIM 在分布式、高并发环境下的数据正确性与安全，系统必须始终严格遵守以下“红线”。

## 1. Safety (安全不变量)
- **Cert Priority**: 在处理任何 Actor (Data-Plane) 状态合并前，必须先同步并应用相关的 Delete Certificate (Control-Plane)。
- **Dominance Rule**: 任何被证书覆盖（Scope/Object 级）的 Actor 必须处于不可见状态，禁止任何 Data-Plane 消息触发其“复活”。
- **Atomic WAL**: 每次 Actor 状态变更必须先持久化到 Oplog (WAL)，成功后方可更新内存快照。

## 2. Ordering (顺序不变量)
- **Monotonic Clocks**: 节点本地逻辑时钟 (Lamport Clock) 必须单调递增。
- **Epoch Barrier**: 禁止时钟低于当前 `Epoch Gate` 的陈旧副本直接进行 `merge_state`。

## 3. Visibility (可见性不变量)
- **Mandatory Filter**: 所有外部检索接口 (`recall`, `search`, `graph_query`) 必须强制通过 `VisibilityResolver` 过滤，禁止绕过证书检查。
- **Double-Layer Check**: 可见性判断必须同时考虑 Actor 本身的 `_deleted` 标记以及 `DeleteCertIndex` 中的全局证书。

## 4. Replication (副本不变量)
- **Convergent State**: 多节点在接收相同消息集（无序）后，最终状态必须强一致（Strong Eventual Consistency）。
- **Idempotency**: 同一证书或同一 ID 的重复消息，合并结果必须保持幂等。

---
*违背以上任何一条不变量，均视为系统严重故障，必须立即触发 Fail-Fast 或 Full Resync。*
