import pytest
import requests
import time
import os
from tests.fixtures.cluster import ClusterFixture

# 辅助断言
def assert_not_contains(memories, mem_id):
    ids = {m["id"] for m in memories}
    assert mem_id not in ids, f"Unexpected visible memory found: {mem_id}"

def assert_contains(memories, mem_id):
    ids = {m["id"] for m in memories}
    assert mem_id in ids, f"Expected memory {mem_id} not found"

@pytest.fixture
def cluster():
    c = ClusterFixture()
    c.start_node("A")
    c.start_node("B")
    c.start_node("C")
    yield c
    c.stop_all()

class TestMIMConflictMatrix:
    """Case 01: Actor 删除 vs 并发更新 (Delete-Wins)"""
    def test_case_01_delete_wins(self, cluster):
        user = "u_e2e"
        m1 = cluster.remember("A", user, "alpha", tag="t1")
        cluster.sync_pair("A", "B", user)
        res_b = cluster.recall("B", user, tag="t1")
        assert_contains(res_b, m1)

        cluster.forget("A", m1)
        cluster.sync_pair("A", "B", user)

        res_a = cluster.recall("A", user, tag="t1")
        res_b = cluster.recall("B", user, tag="t1")
        assert_not_contains(res_a, m1)
        assert_not_contains(res_b, m1)

    """Case 02: 作用域删除 (Parent Dominance)"""
    def test_case_02_parent_dominance(self, cluster):
        user = "u_parent"
        m1 = cluster.remember("A", user, "child-memory")
        # 直接同步证书到 A
        requests.post(f"{cluster.nodes['A']}/v1/sync_certs", json={f"user:{user}": {"scope": f"user:{user}", "policy": "delete_wins"}})
        res = cluster.recall("A", user)
        assert_not_contains(res, m1)

    """Case 03: 时钟回流拒绝 (Epoch Gate)"""
    def test_case_03_epoch_gate(self, cluster):
        user = "u_epoch"
        m1 = cluster.remember("A", user, "modern-content")
        actor_data = {
            "id": m1,
            "owner_id": user,
            "content": {"value": "old-content", "clock": 0, "node_id": "remote"},
            "memory_type": {"value": "fact", "clock": 0, "node_id": "remote"},
            "status": {"value": "active", "clock": 0, "node_id": "remote"},
            "_meta": {"clock": 0, "version_vector": {"remote": 0}},
            "_deleted": False
        }
        # 模拟外部同步陈旧数据
        requests.post(f"{cluster.nodes['A']}/v1/sync_single", json=actor_data)
        res_a = cluster.recall("A", user)
        found = False
        for m in res_a:
            if m["id"] == m1:
                assert m["content"] == "modern-content" # LWW 应保护新内容
                found = True
        assert found

    """Case 04: Index 引用残留 vs 对象已删 (双层过滤)"""
    def test_case_04_double_filter(self, cluster):
        user = "u_df"
        m1 = cluster.remember("A", user, "to-be-deleted")
        cluster.forget("A", m1)
        res = cluster.recall("A", user)
        assert_not_contains(res, m1)

    """Case 06: 最终一致性 (Convergent State)"""
    def test_case_06_convergence(self, cluster):
        user = "u_conv"
        m1 = cluster.remember("A", user, "initial")
        m2 = cluster.remember("B", user, "secondary")

        cluster.sync_all(user)

        res_a = cluster.recall("A", user)
        res_b = cluster.recall("B", user)
        res_c = cluster.recall("C", user)

        assert len(res_a) == len(res_b) == len(res_c) == 2
        ids_a = {m["id"] for m in res_a}
        ids_b = {m["id"] for m in res_b}
        ids_c = {m["id"] for m in res_c}
        assert ids_a == ids_b == ids_c == {m1, m2}

    """Case 09: 重启恢复一致性 (Snapshot + Oplog Replay)"""
    def test_case_09_recovery_consistency(self, cluster):
        user = "u_recover"
        m1 = cluster.remember("A", user, "pre-crash")
        cluster.stop_node("A")
        cluster.start_node("A")
        res = cluster.recall("A", user)
        assert_contains(res, m1)
