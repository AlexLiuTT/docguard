import re
import logging
from typing import List

logger = logging.getLogger("docguard")

_NAME_CONTEXT_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{2,4}(?=\s*(?:先生|女士|律师|法官|仲裁员|委托代理人|被告|原告|申请人|被申请人|证人|鉴定人))"
)

_COMMON_SURNAMES = set(
    "王李张刘陈杨黄赵周吴徐孙马胡朱郭何罗高林梁郑谢唐韩冯董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘"
)

_SUSPECTED_NAME_PATTERN = re.compile(
    r"(?<![[\u4e00-\u9fff])([" + "".join(_COMMON_SURNAMES) + r"][\u4e00-\u9fff]{1,2})(?![\u4e00-\u9fff\]])"
)

def check_residual_names(output_text: str) -> List[str]:
    """扫描脱敏后文本中疑似未替换的人名。"""
    warnings = []
    
    # 1. 扫描上下文模式
    context_matches = _NAME_CONTEXT_PATTERN.findall(output_text)
    if context_matches:
        real_leaks = [m for m in context_matches if "[脱敏]" not in m and "[" not in m]
        if real_leaks:
            warnings.append(f"质量警告：疑似残留姓名（上下文模式）: {', '.join(set(real_leaks[:5]))}")
            
    # 2. 扫描疑似人名（常见姓氏开头）
    suspected = set(_SUSPECTED_NAME_PATTERN.findall(output_text))
    if suspected:
        real_leaks = [s for s in suspected if "[脱敏]" not in s and "[" not in s]
        if len(real_leaks) > 3: # 超过3个才报警，防止太多误报
            warnings.append(f"质量警告：疑似残留人名（常见姓氏模式, 共{len(real_leaks)}个）: {', '.join(real_leaks[:5])}...")
            
    return warnings
