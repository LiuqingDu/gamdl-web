"""
配置管理模块

从环境变量读取配置，提供默认值
"""

import os
from pathlib import Path


class Settings:
    """应用配置类"""

    # 路径配置
    CONFIG_PATH: Path = Path(os.getenv("GAMDL_CONFIG_PATH", "/config"))
    DOWNLOADS_PATH: Path = Path(os.getenv("GAMDL_DOWNLOADS_PATH", "/downloads"))

    # 服务配置
    HOST: str = os.getenv("GAMDL_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("GAMDL_PORT", "5800"))

    # 数据库配置
    @property
    def DATABASE_PATH(self) -> Path:
        return self.CONFIG_PATH / "tasks.db"

    # Cookies配置
    @property
    def COOKIES_PATH(self) -> Path:
        return self.CONFIG_PATH / "cookies.txt"

    def ensure_directories(self) -> None:
        """确保必要的目录存在"""
        self.CONFIG_PATH.mkdir(parents=True, exist_ok=True)
        self.DOWNLOADS_PATH.mkdir(parents=True, exist_ok=True)


# 全局配置实例
settings = Settings()
