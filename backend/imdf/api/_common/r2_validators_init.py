"""R2 验证器集合 (Pydantic + FastAPI 工具)
==========================================

各模块单文件 < 50 行, 全部使用 Pydantic v2 + FastAPI。

模块清单:
  - cron_validator: cron 表达式 + trigger_config 校验
  - webhook_url_validator: URL 合法 + SSRF 防护
  - task_id_validator: 异步任务 ID 命名空间
  - scheduler_validators: 调度历史过滤
  - pagination_compat: 通用分页参数 (兼容层)
  - date_range: 统计/报表日期范围 (R2-5)
  - granularity: 聚合粒度枚举 (R2-5)
  - dimension: 维度白名单 (R2-5)
"""
