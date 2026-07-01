"""属性测试：GlobalMapping、文本替换、Round-Trip"""
import re
import sys
sys.path.insert(0, '/Users/alexliuair/ai_temp/docguard')

import pytest
from hypothesis import given, settings, strategies as st
from reversible.placeholder_registry import GlobalMapping, TYPE_PREFIX
from reversible.anonymizer import _replace_text
from reversible.restorer import restore_text

VALID_TYPES = list(TYPE_PREFIX.keys())

# Property 2
# **Validates: Requirements 2.3**
@given(
    original=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    entity_type=st.sampled_from(VALID_TYPES),
    n_calls=st.integers(min_value=2, max_value=10),
)
def test_property2_idempotent_mapping(original, entity_type, n_calls):
    gm = GlobalMapping(session_id="test", created_at="2025-01-01T00:00:00")
    results = [gm.get_or_create(original, entity_type) for _ in range(n_calls)]
    assert len(set(results)) == 1  # 所有结果相同
    # 该 original 在 mappings 中只有一条
    count = sum(1 for e in gm.mappings.values() if e["original"] == original)
    assert count == 1

# Property 3
# **Validates: Requirements 2.4**
@given(
    originals=st.lists(
        st.text(min_size=1, max_size=30).filter(lambda s: s.strip()),
        min_size=2, max_size=15, unique=True
    ),
    entity_type=st.sampled_from(VALID_TYPES),
)
def test_property3_monotone_counter(originals, entity_type):
    gm = GlobalMapping(session_id="test", created_at="2025-01-01T00:00:00")
    placeholders = [gm.get_or_create(o, entity_type) for o in originals]
    numbers = [int(re.search(r"(\d+)\]\]$", ph).group(1)) for ph in placeholders]
    for i in range(1, len(numbers)):
        assert numbers[i] > numbers[i-1]

# Property 4
# **Validates: Requirements 2.5**
@given(entity_type=st.sampled_from(VALID_TYPES))
def test_property4_placeholder_format(entity_type):
    gm = GlobalMapping(session_id="test", created_at="2025-01-01T00:00:00")
    ph = gm.get_or_create("dummy_entity_for_format_test", entity_type)
    assert re.match(r"^\[\[[A-Z]+\d{3}\]\]$", ph), f"格式不合规: {ph}"
    prefix = TYPE_PREFIX[entity_type]
    assert f"[[{prefix}" in ph

# Property 5
# **Validates: Requirements 4.4**
@given(
    base_text=st.text(min_size=5, max_size=200),
    entities=st.lists(
        st.text(min_size=1, max_size=20).filter(lambda s: s.strip() and "[[" not in s),
        min_size=1, max_size=5, unique=True,
    ),
)
def test_property5_entities_disappear(base_text, entities):
    # 确保实体出现在文本中
    text = base_text
    for i, e in enumerate(entities):
        text = text + e  # 保证实体在文本中
    gm = GlobalMapping(session_id="test", created_at="2025-01-01T00:00:00")
    sorted_entities = sorted(
        [(e, gm.get_or_create(e, "P"), "P") for e in entities],
        key=lambda x: len(x[0]), reverse=True
    )
    result = _replace_text(text, sorted_entities)
    for original, _, _ in sorted_entities:
        assert original not in result, f"实体 {original!r} 未被替换"

# Property 6
# **Validates: Requirements 6.5**
@given(
    base_text=st.text(min_size=1, max_size=200),
    entities=st.lists(
        st.text(min_size=1, max_size=20).filter(lambda s: s.strip() and "[[" not in s),
        min_size=1, max_size=5, unique=True,
    ),
)
def test_property6_roundtrip(base_text, entities):
    text = base_text
    for e in entities:
        text = text + e
    gm = GlobalMapping(session_id="test", created_at="2025-01-01T00:00:00")
    sorted_entities = sorted(
        [(e, gm.get_or_create(e, "P"), "P") for e in entities],
        key=lambda x: len(x[0]), reverse=True
    )
    anonymized = _replace_text(text, sorted_entities)
    restored = restore_text(anonymized, gm)
    assert restored == text, f"Round-Trip 失败"
