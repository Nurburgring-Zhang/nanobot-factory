# P3-5-W2 — 10 评测算子 + 15 采集算子

**Worker**: coder
**Date**: 2026-06-22
**Status**: DONE — 25/25 TestClient smoke PASS (eval 10/10, collect 15/15)

## 完成内容

### 评测算子 (10) — evaluation-service
| ID | 算子 | 算法 | 输出范围 |
|---|---|---|---|
| `eval.image.fid` | FID Frechet Inception Distance | numpy: resize→grayscale→mu/sigma→Frobenius | ≥0 (lower better) |
| `eval.image.clip_score` | CLIP 图文匹配 | token Jaccard + 长度惩罚 + 亮度 | 0-1 |
| `eval.text.bleu` | BLEU-4 n-gram precision | clipped n-gram + brevity penalty | 0-1 |
| `eval.text.rouge` | ROUGE-1/2/L | LCS + n-gram F-measure | 0-1 |
| `eval.text.bert_score` | BERTScore (proxy) | IDF-weighted char-n-gram 贪心 | 0-1 |
| `eval.image.aesthetic` | 美学预测 | brightness+contrast+saturation+symmetry | 1-10 |
| `eval.image.hpsv2` | HPSv2 人类偏好 | alignment+sharpness+cleanness | 0-1 |
| `eval.video.quality` | 视频质量综合 | resolution/fps/stability/sharpness | 0-1 |
| `eval.audio.quality` | 音频质量综合 | SR/SNR/clip/silence/dynamic-range | 0-1 |
| `eval.bad_case.detect` | Bad Case 检测 | 多 metric 阈值规则引擎 | bool + violations |

### 采集算子 (15) — collection-service (新, port 8012)
| ID | 数据源 | 模态 | Live API | 沙箱 |
|---|---|---|---|---|
| `collect.web.crawler` | 任意 URL | html | httpx + HTML strip | mock |
| `collect.video.youtube` | YouTube | video | URL 解析 / yt-dlp | mock |
| `collect.social.twitter` | Twitter/X | text | URL 解析 | mock |
| `collect.video.bilibili` | B 站 | video | URL 解析 | mock |
| `collect.social.instagram` | Instagram | image | URL 解析 | mock |
| `collect.video.tiktok` | TikTok | video | URL 解析 | mock |
| `collect.api.wikipedia` | 维基百科 | text | REST summary | mock |
| `collect.image.unsplash` | Unsplash | image | api.unsplash.com | mock |
| `collect.video.pexels` | Pexels | video | api.pexels.com | mock |
| `collect.media.pixabay` | Pixabay | image/video/audio | pixabay.com/api | mock |
| `collect.web.common_crawl` | Common Crawl | html | CDX index | mock |
| `collect.academic.arxiv` | arXiv | text | export.arxiv.org Atom | mock |
| `collect.code.github` | GitHub | text | api.github.com/search | mock |
| `collect.dataset.kaggle` | Kaggle | dataset | kaggle.com/api | mock |
| `collect.dataset.huggingface` | HuggingFace | dataset | huggingface.co/api | mock |

## 架构要点

- **模式一致**: 沿用 `cleaning-service` (P3-4-W1) 的 `OPERATORS` dict + `OPERATOR_META` + dynamic routing 模式
- **接口**: `run(query, params) -> dict`, `POST /api/v1/collect/{op_id}` + `GET /api/v1/collect/list`
- **沙箱安全**: `IMDF_SANDBOX_MODE=1` 默认开启, 真实网络调用需要显式关闭 + API key
- **依赖**: 仅 fastapi + httpx + numpy + Pillow (全部已有, 无需新增)
- **未拉大模型**: 评测算子全部 deterministic, 无 torch/transformers 依赖; 业务侧可后续替换 `_score_*` 内部函数

## 验证 (TestClient, no live uvicorn)

```
$ python tests/test_p3_5_w2_eval_collection.py
eval pass: 10/10
collect pass: 15/15
ALL PASS
```

## 后续工作 (retry TODO)

1. **生产部署**: 在 `docker-compose.yml` 添加 `collection-service: 8012`
2. **采集 pipeline**: 与 `dispatcher` (P3-3-W2) 集成, 让采集任务真正写入 `imdf.data.assets` 
3. **评测真模型**: 替换为 CLIP/LAION-aesthetic/yt-dlp/torch-fid, 但需先解决 GPU 依赖
4. **认证**: collection-service 暂未接 auth, 生产环境应复用 P3-1-W2 的 API Gateway
5. **CORS / rate limit**: 暂沿用默认 CORS=*, 生产应配白名单
