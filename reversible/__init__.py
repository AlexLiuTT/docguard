"""
reversible — DocGuard 可逆脱敏与还原子包

本包提供以下模块：
- session_manager:    Session 文件夹的创建、枚举与路径管理
- placeholder_registry: GlobalMapping 类，管理占位符与原文的双向映射
- anonymizer:         可逆脱敏核心（NER + 占位符替换 + mapping.json 写入）
- restorer:           还原核心（读取 mapping.json + 占位符逆向替换）
"""
