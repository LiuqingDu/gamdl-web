"""
数据模型模块

定义任务等数据模型
"""

from datetime import datetime, UTC
from sqlmodel import SQLModel, Field


class TaskStatus:
    """任务状态常量"""
    PENDING = 0       # 等待中
    DOWNLOADING = 1   # 下载中
    COMPLETED = 2     # 完成
    ERROR = -1        # 错误
    CANCELLED = -2    # 已取消

    @classmethod
    def to_text(cls, status: int) -> str:
        """状态码转文本"""
        status_map = {
            cls.PENDING: "等待中",
            cls.DOWNLOADING: "下载中",
            cls.COMPLETED: "完成",
            cls.ERROR: "错误",
            cls.CANCELLED: "已取消",
        }
        return status_map.get(status, "未知")


class Task(SQLModel, table=True):
    """任务模型"""
    __tablename__ = "tasks"

    id: str = Field(primary_key=True)  # 从URL提取的ID
    url: str                            # 完整的Apple Music URL
    type: str                           # 类型（artist/album/playlist/song）
    name: str                           # 名称（从URL提取）
    language: str = "zh-CN"             # 语言代码
    status: int = TaskStatus.PENDING    # 状态码
    overwrite: bool = False             # 是否覆盖已有文件
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        """转换为字典，包含状态文本"""
        return {
            "id": self.id,
            "url": self.url,
            "type": self.type,
            "name": self.name,
            "language": self.language,
            "status": self.status,
            "status_text": TaskStatus.to_text(self.status),
            "overwrite": self.overwrite,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
