"""
数据库模块

使用SQLite + SQLModel进行数据持久化
"""

from sqlmodel import SQLModel, create_engine, Session
from contextlib import contextmanager
from typing import Generator

from .config import settings


# 创建数据库引擎
engine = None


def get_engine():
    """获取数据库引擎（懒加载）"""
    global engine
    if engine is None:
        settings.ensure_directories()
        database_url = f"sqlite:///{settings.DATABASE_PATH}"
        engine = create_engine(database_url, echo=False)
    return engine


def init_db() -> None:
    """初始化数据库，创建所有表"""
    from .models import Task  # 延迟导入避免循环依赖
    SQLModel.metadata.create_all(get_engine())


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """获取数据库会话的上下文管理器"""
    with Session(get_engine()) as session:
        yield session


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI依赖注入用的会话生成器"""
    with Session(get_engine()) as session:
        yield session
