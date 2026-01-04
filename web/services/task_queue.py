"""
任务队列服务模块

管理下载任务的队列处理，确保串行执行
"""

import subprocess
import threading
import logging
from datetime import datetime, UTC
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlmodel import select

from ..config import settings
from ..database import get_session
from ..models import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskQueue:
    """任务队列管理器"""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._current_log: str | None = None
        self._log_lock = threading.Lock()
        self._processing = False
        self._processing_lock = threading.Lock()

    def get_current_log(self) -> str | None:
        """获取当前下载日志"""
        with self._log_lock:
            return self._current_log

    def _set_current_log(self, log: str | None) -> None:
        """设置当前下载日志"""
        with self._log_lock:
            self._current_log = log

    def process_next(self) -> None:
        """处理下一个待处理任务"""
        with self._processing_lock:
            if self._processing:
                return
            self._processing = True

        self._executor.submit(self._process_pending_task)

    def _process_pending_task(self) -> None:
        """处理待处理任务的内部方法"""
        try:
            # 获取待处理任务
            with get_session() as session:
                task = session.exec(
                    select(Task).where(Task.status == TaskStatus.PENDING).limit(1)
                ).first()

                if not task:
                    with self._processing_lock:
                        self._processing = False
                    return

                # 更新状态为下载中
                task.status = TaskStatus.DOWNLOADING
                task.updated_at = datetime.now(UTC)
                session.add(task)
                session.commit()

                # 复制任务信息用于下载
                task_id = task.id
                task_url = task.url
                task_language = task.language
                task_name = task.name
                task_overwrite = task.overwrite

            # 执行下载
            self._download_task(task_id, task_url, task_language, task_name, task_overwrite)

        except Exception as e:
            logger.error(f"处理任务时发生错误: {e}")
        finally:
            with self._processing_lock:
                self._processing = False

            # 检查是否还有待处理任务
            with get_session() as session:
                has_pending = session.exec(
                    select(Task).where(Task.status == TaskStatus.PENDING).limit(1)
                ).first()

                if has_pending:
                    self.process_next()

    def _download_task(
        self,
        task_id: str,
        url: str,
        language: str,
        name: str,
        overwrite: bool = False
    ) -> None:
        """执行下载任务"""
        logger.info(f"开始下载任务: {task_id}, 名称: {name}, 语言: {language}, 覆盖: {overwrite}")

        try:
            # 构建下载命令
            output_path = settings.DOWNLOADS_PATH
            cookies_path = settings.COOKIES_PATH
            temp_path = Path(f"/tmp/gamdl_{task_id}")

            command = (
                f'gamdl "{url}" '
                f'-l {language} '
                f'-o {output_path} '
                f'--temp-path {temp_path} '
                f'-c {cookies_path}'
            )

            # 如果设置了覆盖，添加--overwrite参数
            if overwrite:
                command += ' --overwrite'

            logger.info(f"执行命令: {command}")

            # 执行命令
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            # 读取输出
            for line in process.stdout:
                line = line.strip()
                self._set_current_log(line)
                logger.info(f"[{task_id}] {line}")

            process.wait()

            # 根据返回码更新状态
            status = TaskStatus.COMPLETED if process.returncode == 0 else TaskStatus.ERROR

            with get_session() as session:
                task = session.get(Task, task_id)
                if task:
                    task.status = status
                    # 下载成功后重置overwrite为False
                    if status == TaskStatus.COMPLETED:
                        task.overwrite = False
                    task.updated_at = datetime.now(UTC)
                    session.add(task)
                    session.commit()

            if status == TaskStatus.COMPLETED:
                logger.info(f"任务 {task_id} ({name}) 下载成功")
            else:
                logger.error(f"任务 {task_id} ({name}) 下载失败，返回码: {process.returncode}")

        except Exception as e:
            logger.error(f"任务 {task_id} 下载过程中发生错误: {e}")

            with get_session() as session:
                task = session.get(Task, task_id)
                if task:
                    task.status = TaskStatus.ERROR
                    task.updated_at = datetime.now(UTC)
                    session.add(task)
                    session.commit()

        finally:
            self._set_current_log(None)

    def reset_running_tasks(self) -> None:
        """将所有运行中的任务重置为等待状态（程序启动时调用）"""
        with get_session() as session:
            tasks = session.exec(
                select(Task).where(Task.status == TaskStatus.DOWNLOADING)
            ).all()

            for task in tasks:
                task.status = TaskStatus.PENDING
                task.updated_at = datetime.now(UTC)
                session.add(task)

            session.commit()

            if tasks:
                logger.info(f"重置了 {len(tasks)} 个运行中的任务")


# 全局任务队列实例
task_queue = TaskQueue()
