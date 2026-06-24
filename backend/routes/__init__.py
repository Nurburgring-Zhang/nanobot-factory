"""Nanobot Factory Routes — 路由注册中心"""
from fastapi import FastAPI
import logging

logger = logging.getLogger(__name__)

def register_all_routers(app: FastAPI):
    """注册所有路由模块到主应用"""
    from . import auth_routes
    app.include_router(auth_routes.router)
    logger.info("auth routes registered")

    from . import health
    app.include_router(health.router)
    logger.info("health routes registered")

    from . import data_quality
    app.include_router(data_quality.router)
    logger.info("data_quality routes registered")

    from . import data_quality_advanced
    app.include_router(data_quality_advanced.router)
    logger.info("data_quality_advanced routes registered")

    from . import data_controlnet
    app.include_router(data_controlnet.router)
    logger.info("data_controlnet routes registered")

    from . import data_dense_caption
    app.include_router(data_dense_caption.router)
    logger.info("data_dense_caption routes registered")

    from . import data_video
    app.include_router(data_video.router)
    logger.info("data_video routes registered")

    from . import data_benchmark
    app.include_router(data_benchmark.router)
    logger.info("data_benchmark routes registered")

    from . import data_annotation
    app.include_router(data_annotation.router)
    logger.info("data_annotation routes registered")

    from . import data_watermark
    app.include_router(data_watermark.router)
    logger.info("data_watermark routes registered")

    from . import data_dataset
    app.include_router(data_dataset.router)
    logger.info("data_dataset routes registered")

    from . import data_nsfw
    app.include_router(data_nsfw.router)
    logger.info("data_nsfw routes registered")

    from . import data_edit
    app.include_router(data_edit.router)
    logger.info("data_edit routes registered")

    from . import data_face
    app.include_router(data_face.router)
    logger.info("data_face routes registered")

    from . import data_video_quality
    app.include_router(data_video_quality.router)
    logger.info("data_video_quality routes registered")

    from . import data_mllm
    app.include_router(data_mllm.router)
    logger.info("data_mllm routes registered")

    from . import agents
    app.include_router(agents.router)
    logger.info("agents routes registered")

    from . import skills
    app.include_router(skills.router)
    logger.info("skills routes registered")

    from . import v2_zhiying
    app.include_router(v2_zhiying.router)
    logger.info("智影数据工场 v2 routes registered")

    from . import production
    app.include_router(production.router)
    logger.info("production pipeline routes registered")

    from . import agents_v2
    app.include_router(agents_v2.router)
    logger.info("agents v2 routes registered")
