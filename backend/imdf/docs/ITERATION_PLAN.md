# IMDF 开发迭代计划 v1.0 — 基于现状审计

## 项目状态

| 维度 | 状态 |
|------|------|
| 代码规模 | 85MB, 794文件, 120个Python模块 |
| API路由 | 90条 |
| 前端节点 | 47种 |
| 模板资源 | 34套PPT + 95视频 + 33网页 + 103提示词 = 300+ |
| 测试 | 41/41通过 |
| Web UI | HTTP 200 |

## 当前存在的缺陷

### P0(必须修)
1. 前端47种节点只有定义和UI，没有真实的引擎调用逻辑
2. 双AI互审的preReview/postReview在前端只是空壳(调了/imdf/external/list但没真正审查)
3. PPT引擎只有10种模板(Frontend Slides有34套但没整合)

### P1(重要)
4. 3D引擎Scene3DManager的add_avatar/camera/occlusion接口参数不统一(上层/下层API签名不一致)
5. cloud_storage的COS签名函数sign_cos_request参数名不与实际使用对齐
6. 前端画布没有持久化(刷新就丢所有节点)
7. 执行日志面板(execPanel)显示隐藏逻辑没完全接好

### P2(需要做)
8. 没有用户认证/多用户
9. 画布协作功能
10. 版本历史只在前端有undo/redo，没有后端持久化
11. 没有Docker部署配置

## 迭代计划

### Iteration 1: 修复P0缺陷(当前)
- 前端节点调通真实API
- 双审前端逻辑补全
- PPT引擎整合34套Frontend Slides模板

### Iteration 2: 修复P1缺陷
- 3D引擎API统一
- 云存储签名修复
- 画布持久化
- 执行面板修复

### Iteration 3: 新增P2功能
- Docker部署
- 用户认证
- 画布协作
