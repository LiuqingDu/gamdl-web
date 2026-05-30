"""
任务队列服务模块

管理下载任务的队列处理，确保串行执行
"""

import subprocess
import threading
import logging
import time
from datetime import datetime, timezone
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
            # 获取待处理任务（按 created_at 降序，优先下载最近创建的任务）
            with get_session() as session:
                task = session.exec(
                    select(Task)
                    .where(Task.status == TaskStatus.PENDING)
                    .order_by(Task.created_at.desc())
                    .limit(1)
                ).first()

                if not task:
                    with self._processing_lock:
                        self._processing = False
                    return

                # 更新状态为下载中
                task.status = TaskStatus.DOWNLOADING
                task.updated_at = datetime.now(timezone.utc)
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
                    select(Task)
                    .where(Task.status == TaskStatus.PENDING)
                    .order_by(Task.created_at.desc())
                    .limit(1)
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

        max_retries = 3
        status = TaskStatus.ERROR
        last_is_429 = False

        try:
            # 构建下载命令

            config_file_path = settings.CONFIG_FILE_PATH
            cookies_path = settings.COOKIES_PATH
            output_path = settings.DOWNLOADS_PATH
            database_path = settings.GAMDL_DATABASE_PATH

            # 根据语言选择对应的 wrapper 服务
            if "zh" in language.lower():
                wrapper_url = "http://wrapper-zh:80"
            else:
                wrapper_url = "http://wrapper-en:80"

            # 用户要求的简洁命令格式：gamdl ${url} --config-path ${config路径} -l ${language}
            command = (
                f'gamdl "{url}" '
                f'--config-path "{config_file_path}" '
                f'-c "{cookies_path}" '
                f'-o "{output_path}" '
                f'--database-path "{database_path}" '
                f'--wrapper-url "{wrapper_url}" '
                f'-l {language}'
            )

            # 如果设置了覆盖，添加--overwrite参数
            if overwrite:
                command += ' --overwrite'

            for attempt in range(max_retries + 1):
                if attempt > 0:
                    logger.info(f"执行命令 (第 {attempt}/{max_retries} 次重试): {command}")
                    self._set_current_log(f"开始下载 (第 {attempt}/{max_retries} 次重试)...")
                else:
                    logger.info(f"执行命令 (首次尝试): {command}")
                    self._set_current_log("开始下载...")

                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )

                output_log = []
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        output_log.append(line)
                        self._set_current_log(line)
                        logger.info(f"[{task_id}] {line}")

                process.wait()

                if process.returncode == 0:
                    status = TaskStatus.COMPLETED
                    last_is_429 = False
                    break
                else:
                    full_output = " ".join(output_log)
                    is_429 = "429" in full_output or "Too Many Requests" in full_output
                    last_is_429 = is_429

                    if attempt < max_retries:
                        if is_429:
                            # 429重试间隔：第1次1分钟(60s)，第2次2分钟(120s)，第3次3分钟(180s)
                            wait_seconds = (attempt + 1) * 60
                            reason = "触发频率限制(429)"
                        else:
                            # 其他普通错误间隔 10s
                            wait_seconds = 10
                            reason = f"异常错误 (返回码 {process.returncode})"

                        logger.warning(f"任务 {task_id} 下载失败 [{reason}]，准备在 {wait_seconds} 秒后进行第 {attempt + 1}/{max_retries} 次重试...")

                        for rem in range(wait_seconds, 0, -1):
                            self._set_current_log(f"下载异常 [{reason}]，等待 {rem}s 后重试 ({attempt + 1}/{max_retries})...")
                            time.sleep(1)
                    else:
                        logger.error(f"任务 {task_id} 经过 {max_retries} 次重试后最终失败。")
                        status = TaskStatus.ERROR

            # 更新数据库状态
            with get_session() as session:
                task = session.get(Task, task_id)
                if task:
                    task.status = status
                    # 下载成功后重置overwrite为False
                    if status == TaskStatus.COMPLETED:
                        task.overwrite = False
                    task.updated_at = datetime.now(timezone.utc)
                    session.add(task)
                    session.commit()

            if status == TaskStatus.COMPLETED:
                logger.info(f"任务 {task_id} ({name}) 下载成功")
                # 成功后，常规冷却缓冲 3 秒
                self._set_current_log("任务结束，冷却缓冲中 (3s)...")
                time.sleep(3)
            else:
                logger.error(f"任务 {task_id} ({name}) 下载最终失败")
                # 如果三次重试依然失败且触发了 429，则在继续下一个任务前强制等待 3 分钟 (180s)
                if last_is_429:
                    logger.warning(f"任务 {task_id} 遭遇严重限流失败，暂停队列 3 分钟后继续处理下一个任务...")
                    for rem in range(180, 0, -1):
                        self._set_current_log(f"遭遇频繁请求限制，队列冷却缓冲中 ({rem}s)...")
                        time.sleep(1)
                else:
                    self._set_current_log("任务下载失败，缓冲中 (3s)...")
                    time.sleep(3)

        except Exception as e:
            logger.error(f"任务 {task_id} 下载过程中发生错误: {e}")

            with get_session() as session:
                task = session.get(Task, task_id)
                if task:
                    task.status = TaskStatus.ERROR
                    task.updated_at = datetime.now(timezone.utc)
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
                task.updated_at = datetime.now(timezone.utc)
                session.add(task)

            session.commit()

            if tasks:
                logger.info(f"重置了 {len(tasks)} 个运行中的任务")


# 全局任务队列实例
task_queue = TaskQueue()
