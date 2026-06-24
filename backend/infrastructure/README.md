---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3045022100d86cd4a911ac828315b8cd3f9e5cffe81c436438f361dc7cedf175038b26e9510220141e3a5350689dc0e8be5d2fb43a4d31873ba4b7051e7d353857ab8847de113b
    ReservedCode2: 3044022060daf3e61fedbb59c1b1a72b74e6145e9d67046773bfbfd99003eddefb178fcd022009367f7249961c5d406d72083aa2d154417b597edb63cedc1c29429dbfdab766
---

# Nanobot Factory Data Infrastructure Layer

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements-data-infra.txt

# 2. 启动所有服务（自动Docker编排）
python -m infrastructure.orchestrator start

# 3. 运行数据库迁移
python -m infrastructure.database.migrations upgrade head
```

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Nanobot Factory                           │
├─────────────────────────────────────────────────────────────┤
│  Production Agents (AI驱动)                                  │
├─────────────────────────────────────────────────────────────┤
│  Skills System │ Unified Generation Service │ Chat System    │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────┐  ┌──────────┐             │
│  │ PostgreSQL  │  │  Redis   │  │ RabbitMQ │             │
│  │  (大脑)     │  │  (反射)  │  │  (神经)  │             │
│  └─────────────┘  └──────────┘  └──────────┘             │
│  ┌─────────────────────────────────────────┐               │
│  │           S3/OSS (存储)                  │               │
│  └─────────────────────────────────────────┘               │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure Layer (Python模块)                          │
└─────────────────────────────────────────────────────────────┘
```

## 核心组件

| 组件 | 作用 | Python模块 |
|------|------|-----------|
| PostgreSQL | 高并发数据存储，向量存储(AI记忆) | `infrastructure.database` |
| Redis | 缓存、会话、状态管理、分布式锁 | `infrastructure.cache` |
| RabbitMQ | 异步任务队列，消息通信 | `infrastructure.queue` |
| S3/OSS | 海量资产存储 | `infrastructure.storage` |

## AI驱动特性

- **智能查询**: 自然语言转SQL (Text-to-SQL)
- **向量存储**: Agent记忆和语义搜索 (PGVector)
- **自适应缓存**: AI预测性缓存
- **自愈模式**: AI自动修复数据库问题
