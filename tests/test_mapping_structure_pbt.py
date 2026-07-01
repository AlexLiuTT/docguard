"""属性测试：mapping.json 结构完整性（Property 7）和追加不覆盖（Property 8）

**Validates: Requirements 5.1, 5.2**
"""
import sys
sys.path.insert(0, '/Users/alexliuair/ai_temp/docguard')

from hypothesis import given, settings, strategies as st
from reversible.placeholder_registry import GlobalMapping, TYPE_PREFIX

VALID_TYPES = list(TYPE_PREFIX.keys())


# Property 7：mapping.json 结构完整性
@given(
    entities=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=30).filter(lambda s: s.strip()),
            st.sampled_from(VALID_TYPES),
        ),
        min_size=1, max_size=10, unique_by=lambda x: x[0],
    )
)
@settings(max_examples=100)
def test_property7_mapping_structure(entities):
    """to_dict() 输出必须包含三个顶层字段，每个 mappings 条目含 original 和合法 type"""
    gm = GlobalMapping(session_id="test_session", created_at="2025-01-01T00:00:00+00:00")
    for original, etype in entities:
        gm.get_or_create(original, etype)

    d = gm.to_dict()
    # 三个顶层字段
    assert "session_id" in d
    assert "created_at" in d
    assert "mappings" in d

    # 每个条目有 original 和 type
    for ph, entry in d["mappings"].items():
        assert "original" in entry, f"缺少 original: {ph}"
        assert "type" in entry, f"缺少 type: {ph}"
        assert entry["type"] in VALID_TYPES, f"type 值不合法: {entry['type']}"


# Property 8：mapping 追加不覆盖已有条目
@given(
    first_batch=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
            st.sampled_from(VALID_TYPES),
        ),
        min_size=1, max_size=5, unique_by=lambda x: x[0],
    ),
    second_batch=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
            st.sampled_from(VALID_TYPES),
        ),
        min_size=1, max_size=5, unique_by=lambda x: x[0],
    ),
)
@settings(max_examples=100)
def test_property8_append_does_not_overwrite(first_batch, second_batch):
    """追加新实体后，已有条目的 original 和 type 值保持不变"""
    gm = GlobalMapping(session_id="test_session", created_at="2025-01-01T00:00:00+00:00")

    # 第一批：记录初始映射
    snapshots = {}
    for original, etype in first_batch:
        ph = gm.get_or_create(original, etype)
        snapshots[ph] = {"original": original, "type": etype}

    # 第二批：追加（可能与第一批有重叠，但重叠的应复用）
    for original, etype in second_batch:
        gm.get_or_create(original, etype)

    # 验证第一批的条目未被修改
    for ph, expected in snapshots.items():
        assert ph in gm.mappings, f"占位符 {ph} 丢失"
        assert gm.mappings[ph]["original"] == expected["original"], f"original 被修改: {ph}"
        assert gm.mappings[ph]["type"] == expected["type"], f"type 被修改: {ph}"
