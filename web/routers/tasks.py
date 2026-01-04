"""
任务API路由模块
"""

import re
import logging
from datetime import datetime, UTC
from urllib.parse import unquote
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..database import get_db_session
from ..models import Task, TaskStatus
from ..schemas import (
    TaskCreate, TaskResponse, TaskListResponse,
    LanguageUpdate, MessageResponse
)
from ..services.task_queue import task_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# URL解析正则
VALID_URL_RE = re.compile(
    r"/([a-z]{2})/(artist|album|playlist|song|music-video|post)/([^/]*)(?:/([^/?]*))?(?:\?i=)?([0-9a-z]*)?"
)


def extract_url_parts(url: str) -> dict | None:
    """
    从Apple Music URL中提取信息

    Returns:
        dict: 包含type, name, id的字典，解析失败返回None
    """
    match = VALID_URL_RE.search(url)
    if not match:
        return None

    url_type = match.group(2)
    # 解码URL中的中文名称
    name = unquote(match.group(3))
    url_id = match.group(4) if match.group(4) else match.group(5)

    return {
        "type": url_type,
        "name": name,
        "id": url_id
    }


def assemble_url(url_type: str, name: str, url_id: str) -> str:
    """组装完整的Apple Music URL"""
    return f"https://music.apple.com/us/{url_type}/{name}/{url_id}"


@router.get("", response_model=TaskListResponse)
def get_tasks(session: Session = Depends(get_db_session)):
    """获取所有任务列表"""
    tasks = session.exec(select(Task)).all()
    return TaskListResponse(
        tasks=[TaskResponse(**task.to_dict()) for task in tasks],
        current_log=task_queue.get_current_log()
    )


@router.post("", response_model=TaskResponse)
def create_task(task_data: TaskCreate, session: Session = Depends(get_db_session)):
    """创建新任务"""
    url_parts = extract_url_parts(task_data.url)
    if not url_parts or not url_parts["id"]:
        raise HTTPException(status_code=400, detail="无效的Apple Music URL")

    # 检查语言是否有效
    valid_languages = ["zh-CN", "en-US"]
    if task_data.language not in valid_languages:
        raise HTTPException(status_code=400, detail=f"不支持的语言: {task_data.language}")

    task_id = url_parts["id"]

    # 检查任务是否已存在
    existing_task = session.get(Task, task_id)
    if existing_task:
        # 更新语言和状态
        existing_task.language = task_data.language
        existing_task.status = TaskStatus.PENDING
        existing_task.updated_at = datetime.now(UTC)
        session.add(existing_task)
        session.commit()
        session.refresh(existing_task)
        logger.info(f"任务已存在，更新任务: {task_id}")

        # 触发处理
        task_queue.process_next()
        return TaskResponse(**existing_task.to_dict())

    # 创建新任务
    task = Task(
        id=task_id,
        url=task_data.url,
        type=url_parts["type"],
        name=url_parts["name"],
        language=task_data.language,
        status=TaskStatus.PENDING,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    logger.info(f"创建新任务: {task_id}, 名称: {url_parts['name']}")

    # 触发处理
    task_queue.process_next()

    return TaskResponse(**task.to_dict())


@router.delete("/{task_id}", response_model=MessageResponse)
def delete_task(task_id: str, session: Session = Depends(get_db_session)):
    """删除任务"""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status == TaskStatus.DOWNLOADING:
        raise HTTPException(status_code=400, detail="无法删除正在下载的任务")

    session.delete(task)
    session.commit()

    logger.info(f"删除任务: {task_id}")
    return MessageResponse(message=f"任务 {task.name} 已删除")


@router.post("/{task_id}/restart", response_model=MessageResponse)
def restart_task(task_id: str, session: Session = Depends(get_db_session)):
    """重启任务"""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status not in [TaskStatus.ERROR, TaskStatus.CANCELLED, TaskStatus.COMPLETED]:
        raise HTTPException(status_code=400, detail="当前状态不允许重启")

    task.status = TaskStatus.PENDING
    task.overwrite = False  # 普通重启不覆盖
    task.updated_at = datetime.now(UTC)
    session.add(task)
    session.commit()

    logger.info(f"重启任务: {task_id}")

    # 触发处理
    task_queue.process_next()

    return MessageResponse(message=f"任务 {task.name} 已重启")


@router.post("/{task_id}/restart-overwrite", response_model=MessageResponse)
def restart_task_with_overwrite(task_id: str, session: Session = Depends(get_db_session)):
    """覆盖重启任务（会覆盖已有文件）"""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status not in [TaskStatus.ERROR, TaskStatus.CANCELLED, TaskStatus.COMPLETED]:
        raise HTTPException(status_code=400, detail="当前状态不允许重启")

    task.status = TaskStatus.PENDING
    task.overwrite = True  # 覆盖重启
    task.updated_at = datetime.now(UTC)
    session.add(task)
    session.commit()

    logger.info(f"覆盖重启任务: {task_id}")

    # 触发处理
    task_queue.process_next()

    return MessageResponse(message=f"任务 {task.name} 已重启（覆盖模式）")


@router.post("/{task_id}/cancel", response_model=MessageResponse)
def cancel_task(task_id: str, session: Session = Depends(get_db_session)):
    """取消任务"""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status != TaskStatus.PENDING:
        raise HTTPException(status_code=400, detail="只能取消等待中的任务")

    task.status = TaskStatus.CANCELLED
    task.updated_at = datetime.now(UTC)
    session.add(task)
    session.commit()

    logger.info(f"取消任务: {task_id}")
    return MessageResponse(message=f"任务 {task.name} 已取消")


@router.patch("/{task_id}/language", response_model=MessageResponse)
def update_language(
    task_id: str,
    data: LanguageUpdate,
    session: Session = Depends(get_db_session)
):
    """更新任务语言"""
    valid_languages = ["zh-CN", "en-US"]
    if data.language not in valid_languages:
        raise HTTPException(status_code=400, detail=f"不支持的语言: {data.language}")

    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task.language = data.language
    task.updated_at = datetime.now(UTC)
    session.add(task)
    session.commit()

    logger.info(f"更新任务语言: {task_id} -> {data.language}")
    return MessageResponse(message=f"任务 {task.name} 的语言已更新为 {data.language}")


@router.post("/reset-all", response_model=MessageResponse)
def reset_all_tasks(session: Session = Depends(get_db_session)):
    """重置所有非运行中的任务为等待状态"""
    tasks = session.exec(
        select(Task).where(Task.status != TaskStatus.DOWNLOADING)
    ).all()

    count = 0
    for task in tasks:
        task.status = TaskStatus.PENDING
        task.updated_at = datetime.now(UTC)
        session.add(task)
        count += 1

    session.commit()

    logger.info(f"重置了 {count} 个任务")

    # 触发处理
    task_queue.process_next()

    return MessageResponse(message=f"已重置 {count} 个任务")
