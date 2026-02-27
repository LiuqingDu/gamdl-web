"""
Pydantic模型模块

定义API请求和响应的数据模型
"""

from pydantic import BaseModel
from typing import Optional, List


class TaskCreate(BaseModel):
    """创建任务请求"""
    url: str
    language: str = "zh-CN"


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    url: str
    type: str
    name: str
    language: str
    status: int
    status_text: str
    overwrite: bool
    created_at: str
    updated_at: str


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[TaskResponse]
    current_log: Optional[str] = None


class LanguageUpdate(BaseModel):
    """更新语言请求"""
    language: str


class CookiesUpdate(BaseModel):
    """更新Cookies请求"""
    content: str


class CookiesStatus(BaseModel):
    """Cookies状态响应"""
    configured: bool
    path: str


class MessageResponse(BaseModel):
    """通用消息响应"""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    success: bool = False
