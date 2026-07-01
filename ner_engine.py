import os
import re
import json
import logging
from typing import List, Set
from openai import OpenAI

# 优先读取环境变量，默认连接本地的 LM Studio
API_BASE = os.getenv("DOCGUARD_API_BASE", "http://localhost:1234/v1")
API_KEY = os.getenv("DOCGUARD_API_KEY", "lm-studio")
MODEL_NAME = os.getenv("DOCGUARD_MODEL", "qwen2.5-14b-instruct-1m")

logger = logging.getLogger("docguard")
_client = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=API_BASE, api_key=API_KEY)
    return _client

SYSTEM_PROMPT = """你是一个极其严谨的法律文书信息提取专家。你的核心任务是100%识别文本中的隐私实体，特别是【自然人姓名】和【联系方式】，绝不能有任何遗漏！

【提取规则】
你需要提取出以下类别的实体，并且严格保持它们在原文中的原始文本（严禁任何缩写或修改）：
1. 自然人姓名（警告：无论是当事人、代理律师、法官、亲属、同事等，只要是人名，必须强制提取！）
2. 公司/企业/机构名称
3. 具体金额（必须含有元/万元等单位，或紧跟在"金额："后面，不要提取纯数字如"4"、"3"）
4. 详细地址/门牌号（必须包含省/市/区/街道/路/号/栋/室等地址要素，至少5个字符）
5. 联系方式（手机号、座机号、邮箱）、证件号（身份证号、护照号）、银行账号

【特别注意】
- 手机号（11位数字，1开头）必须提取到 ids 列表中
- 身份证号（18位）必须提取到 ids 列表中
- 地址可能跨行，仍需完整提取
- 金额不要提取孤立的个位数字（如"4"、"3"）

【输出格式】
你必须且只能输出一个合法的 JSON 对象，不包含任何解释文字。格式如下：
{
  "names": ["张三", "李四"],
  "companies": ["某某公司"],
  "amounts": ["1000元"],
  "addresses": ["北京市朝阳区..."],
  "ids": ["1101051990...", "13800138000"]
}
如果没有某个类别的实体，请返回空列表 []。绝对不要返回除 JSON 之外的任何字符。
"""

# ── 正则兜底：LLM 漏检时用正则补采 ──
_PHONE_RE = re.compile(r'1[3-9]\d{9}')
_ID_CARD_RE = re.compile(r'\d{17}[\dXx]')
_BANK_CARD_RE = re.compile(r'\b\d{16,19}\b')

# 噪声过滤：过短的纯数字（如 "4"、"3"）不应作为金额
_NOISE_AMOUNT_RE = re.compile(r'^\d{1,2}$')


def _normalize_ws(s: str) -> str:
    """去除所有空白字符，用于跨行实体匹配。"""
    return re.sub(r'\s+', '', s)


def _regex_fallback(text: str) -> list[tuple[str, str]]:
    """
    正则兜底提取：LLM 可能漏检手机号、身份证号、银行卡号。
    返回 [(entity_text, entity_type), ...]。
    """
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for m in _PHONE_RE.finditer(text):
        val = m.group()
        if val not in seen:
            results.append((val, "ID"))
            seen.add(val)

    for m in _ID_CARD_RE.finditer(text):
        val = m.group()
        if val not in seen:
            results.append((val, "ID"))
            seen.add(val)

    return results


def _filter_noise(entities: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """过滤明显噪声实体。"""
    filtered = []
    for original, etype in entities:
        # 纯数字 1-2 位的金额 → 噪声
        if etype == "AMT" and _NOISE_AMOUNT_RE.match(original.strip()):
            continue
        # 过短的非数字实体（单字符）→ 噪声
        if len(original.strip()) <= 1:
            continue
        filtered.append((original, etype))
    return filtered

def extract_entities_from_chunk(text_chunk: str) -> List[str]:
    """对单个文本块调用 LLM 进行实体提取，返回该块所有的实体字符串。"""
    if not text_chunk.strip():
        return []

    normalized_chunk = _normalize_ws(text_chunk)

    try:
        response = get_client().chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text_chunk},
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content
        if not content:
            return []
        
        # 尝试解析 JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # 容错：有些模型可能加上了 markdown 的 ```json ... ```
            content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)

        entities = []
        for key, value_list in data.items():
            if isinstance(value_list, list):
                for v in value_list:
                    if isinstance(v, str) and v.strip():
                        # 空白归一化后匹配，解决跨行实体被过滤的问题
                        if _normalize_ws(v.strip()) in normalized_chunk:
                            entities.append(v.strip())
        return entities
    except Exception as e:
        logger.error(f"AI 调用提取失败: {e}")
        return []

def extract_all_entities(text_chunks: List[str]) -> List[str]:
    """合并去重所有实体，并按长度降序排列。"""
    all_entities: Set[str] = set()
    for i, chunk in enumerate(text_chunks, 1):
        logger.info(f"    - LLM 实体抽取 第 {i}/{len(text_chunks)} 块...")
        extracted = extract_entities_from_chunk(chunk)
        all_entities.update(extracted)
    
    # 按照长度降序排列，避免子字符串替换问题（如优先替换“张三律师”然后再考虑“张三”）
    sorted_entities = sorted(list(all_entities), key=len, reverse=True)
    return sorted_entities


# TYPE_MAP: JSON 字段名 → 实体类型代码
_TYPE_MAP: dict[str, str] = {
    "names":     "P",
    "companies": "ORG",
    "amounts":   "AMT",
    "addresses": "LOC",
    "ids":       "ID",
}

def extract_entities_with_types_from_chunk(text_chunk: str) -> list[tuple[str, str]]:
    """
    对单个文本块调用 LLM 进行实体提取，返回 (entity_text, entity_type) 元组列表。
    复用现有 get_client()、SYSTEM_PROMPT 和 JSON 解析逻辑。
    TYPE_MAP: names→P, companies→ORG, amounts→AMT, addresses→LOC, ids→ID
    过滤空字符串，只返回出现在原文 text_chunk 中的实体（空白归一化后匹配）。
    """
    if not text_chunk.strip():
        return []

    normalized_chunk = _normalize_ws(text_chunk)
    result: list[tuple[str, str]] = []

    try:
        response = get_client().chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text_chunk},
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content
        if not content:
            return []

        # 尝试解析 JSON，容错 markdown 代码块
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)

        for field_name, entity_type in _TYPE_MAP.items():
            value_list = data.get(field_name, [])
            if isinstance(value_list, list):
                for v in value_list:
                    if isinstance(v, str) and v.strip():
                        # 空白归一化后匹配，解决跨行实体被过滤的问题
                        if _normalize_ws(v.strip()) in normalized_chunk:
                            result.append((v.strip(), entity_type))
    except Exception as e:
        logger.error(f"AI 调用提取失败 (with types): {e}")

    # 正则兜底：补充 LLM 漏检的手机号、身份证号
    regex_entities = _regex_fallback(text_chunk)
    for val, etype in regex_entities:
        if not any(_normalize_ws(val) == _normalize_ws(r[0]) for r in result):
            result.append((val, etype))

    return result


def extract_entities_with_types(text_chunks: list[str]) -> list[tuple[str, str]]:
    """
    合并去重所有 chunks 的实体（含类型），按 original 长度降序返回。
    相同 original 以首次出现的类型为准（去重逻辑）。
    与现有 extract_all_entities 规律保持一致。
    """
    all_entities: dict[str, str] = {}  # original -> type（首次出现优先）
    for i, chunk in enumerate(text_chunks, 1):
        logger.info(f"    - LLM 实体抽取（含类型）第 {i}/{len(text_chunks)} 块...")
        extracted = extract_entities_with_types_from_chunk(chunk)
        for original, entity_type in extracted:
            if original not in all_entities:
                all_entities[original] = entity_type

    # 噪声过滤
    entity_list = list(all_entities.items())
    entity_list = _filter_noise(entity_list)
    if len(entity_list) < len(all_entities):
        removed = len(all_entities) - len(entity_list)
        logger.info(f"    🧹 已过滤 {removed} 个噪声实体")

    # 按照长度降序排列，避免子字符串替换问题（如优先替换"张三律师"然后再考虑"张三"）
    sorted_pairs = sorted(entity_list, key=lambda x: len(x[0]), reverse=True)
    return sorted_pairs
