"""
设置API路由模块
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..config import settings
from ..schemas import CookiesUpdate, CookiesStatus, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/cookies", response_model=CookiesStatus)
def get_cookies_status():
    """获取Cookies配置状态"""
    configured = settings.COOKIES_PATH.exists()
    return CookiesStatus(
        configured=configured,
        path=str(settings.COOKIES_PATH)
    )


@router.post("/cookies", response_model=MessageResponse)
def update_cookies(data: CookiesUpdate):
    """更新Cookies内容"""
    try:
        # 确保目录存在
        settings.ensure_directories()

        # 写入cookies文件
        settings.COOKIES_PATH.write_text(data.content, encoding="utf-8")

        logger.info(f"Cookies已更新: {settings.COOKIES_PATH}")
        return MessageResponse(message="Cookies已保存")

    except Exception as e:
        logger.error(f"保存Cookies失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.get("/cookies/content")
def get_cookies_content():
    """获取Cookies内容（用于编辑）"""
    if not settings.COOKIES_PATH.exists():
        return JSONResponse(content={"content": ""})

    try:
        content = settings.COOKIES_PATH.read_text(encoding="utf-8")
        return JSONResponse(content={"content": content})
    except Exception as e:
        logger.error(f"读取Cookies失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取失败: {str(e)}")


# ============ Config.ini 设置 ============

@router.get("/config")
def get_config_status():
    """获取配置文件状态"""
    config_path = settings.CONFIG_PATH / "config.ini"
    configured = config_path.exists()
    return JSONResponse(content={
        "configured": configured,
        "path": str(config_path)
    })


@router.get("/config/content")
def get_config_content():
    """获取config.ini内容（用于编辑）"""
    config_path = settings.CONFIG_PATH / "config.ini"
    if not config_path.exists():
        return JSONResponse(content={"content": ""})

    try:
        content = config_path.read_text(encoding="utf-8")
        return JSONResponse(content={"content": content})
    except Exception as e:
        logger.error(f"读取config.ini失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取失败: {str(e)}")


@router.post("/config", response_model=MessageResponse)
def update_config(data: CookiesUpdate):
    """更新config.ini内容"""
    try:
        # 确保目录存在
        settings.ensure_directories()

        config_path = settings.CONFIG_PATH / "config.ini"
        # 写入配置文件
        config_path.write_text(data.content, encoding="utf-8")

        logger.info(f"config.ini已更新: {config_path}")
        return MessageResponse(message="配置已保存")

    except Exception as e:
        logger.error(f"保存config.ini失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")
