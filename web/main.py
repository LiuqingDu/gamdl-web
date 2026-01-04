"""
FastAPI 应用入口

Apple Music Web 下载器的主入口文件
"""

import sys
import logging
import subprocess
import shutil
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from .config import settings
from .database import init_db
from .routers import tasks, settings as settings_router
from .services.task_queue import task_queue

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("启动 Apple Music 下载器服务")

    # 确保目录存在
    settings.ensure_directories()
    logger.info(f"配置路径: {settings.CONFIG_PATH}")
    logger.info(f"下载路径: {settings.DOWNLOADS_PATH}")

    # 检查并初始化 config.ini
    await init_config()

    # 初始化数据库
    init_db()
    logger.info("数据库初始化完成")

    # 重置运行中的任务
    task_queue.reset_running_tasks()

    # 处理待处理任务
    task_queue.process_next()
    logger.info("开始处理待处理任务")

    logger.info(f"服务启动完成，监听 {settings.HOST}:{settings.PORT}")

    yield

    # 关闭时
    logger.info("服务正在关闭...")


async def init_config():
    """初始化配置文件"""

    config_ini_path = settings.CONFIG_PATH / "config.ini"

    if config_ini_path.exists():
        logger.info("config.ini 已存在")
        return

    logger.info("config.ini 不存在，正在初始化...")

    # 运行 gamdl 生成默认配置（会在 ~/.gamdl/config.ini 生成）
    try:
        # 运行一次无参数的 gamdl，它会自动创建配置文件
        process = subprocess.run(
            ["gamdl", "--help"],  # 使用 --help 避免交互
            capture_output=True,
            text=True,
            timeout=30
        )

        # 默认配置文件路径
        default_config = Path.home() / ".gamdl" / "config.ini"

        if default_config.exists():
            # 复制到 config 目录
            shutil.copy(default_config, config_ini_path)
            logger.info(f"已复制 config.ini 到 {config_ini_path}")
        else:
            # 如果默认位置也没有，创建一个空的配置文件
            config_ini_path.touch()
            logger.warning("未找到默认配置文件，已创建空的 config.ini")

    except Exception as e:
        logger.error(f"初始化 config.ini 失败: {e}")


# 创建FastAPI应用
app = FastAPI(
    title="Apple Music 下载器",
    description="Apple Music 歌曲下载 Web 服务",
    version="1.0.0",
    lifespan=lifespan
)

# 注册路由
app.include_router(tasks.router)
app.include_router(settings_router.router)


# 健康检查
@app.get("/api/health")
def health_check():
    """健康检查接口"""
    return {"status": "ok"}


# 静态文件服务
static_path = Path(__file__).parent / "static"

# 挂载静态资源
app.mount("/css", StaticFiles(directory=static_path / "css"), name="css")
app.mount("/js", StaticFiles(directory=static_path / "js"), name="js")


# 主页
@app.get("/")
def index():
    """主页"""
    return FileResponse(static_path / "index.html")


def main():
    """主函数"""
    uvicorn.run(
        "web.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False
    )


if __name__ == "__main__":
    main()
