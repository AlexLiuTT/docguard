import os
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

SYSTEM_PROMPT = """
你是一个极其严谨的法律文书信息提取专家。你的核心任务是100%识别文本中的隐私实体，特别是【自然人姓名】，绝不能有任何遗漏！

【提取规则】
你需要提取出以下类别的实体，并且严格保持它们在原文中的原始文本（严禁任何缩写或修改）：
1. 自然人姓名（警告：无论是当事人、代理律师、法官、亲属、同事等，只要是人名，必须强制提取！）
2. 公司/企业/机构名称
3. 具体金额
4. 详细地址/门牌号
5. 联系方式/证件号/银行账号

【输出格式】
你必须且只能输出一个合法的 JSON 对象，不包含任何解释文字。格式如下：
{
  "names": ["张三", "李四"],
  "companies": ["某某公司"],
  "amounts": ["1000元"],
  "addresses": ["北京市朝阳区..."],
  "ids": ["1101051990..."]
}
如果没有某个类别的实体，请返回空列表 []。绝对不要返回除 JSON 之外的任何字符。
"""

def extract_entities_from_chunk(text_chunk: str) -> List[str]:
    """对单个文本块调用 LLM 进行实体提取，返回该块所有的实体字符串。"""
    if not text_chunk.strip():
        return []

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
                    if isinstance(v, str) and v.strip() and v.strip() in text_chunk:
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
    过滤空字符串，只返回出现在原文 text_chunk 中的实体。
    """
    if not text_chunk.strip():
        return []

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

        result: list[tuple[str, str]] = []
        for field_name, entity_type in _TYPE_MAP.items():
            value_list = data.get(field_name, [])
            if isinstance(value_list, list):
                for v in value_list:
                    if isinstance(v, str) and v.strip() and v.strip() in text_chunk:
                        result.append((v.strip(), entity_type))
        return result
    except Exception as e:
        logger.error(f"AI 调用提取失败 (with types): {e}")
        return []


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

    # 按照长度降序排列，避免子字符串替换问题（如优先替换"张三律师"然后再考虑"张三"）
    sorted_pairs = sorted(all_entities.items(), key=lambda x: len(x[0]), reverse=True)
    return sorted_pairs
