# 使用官方 Python 3.11 精简版作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 从官方镜像复制 uv 包管理器到当前镜像
# uv 是一个快速的 Python 包管理工具，用于替代 pip
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 复制二进制工具到系统路径
# 这些是 ffmpeg 相关工具，用于媒体处理和解密
COPY binaries/amd64/* /usr/local/bin/

# 给二进制文件添加执行权限
# ffmpeg: 媒体格式转换工具
# ffprobe: 媒体文件信息探测工具
# mp4decrypt: MP4 解密工具
RUN chmod +x /usr/local/bin/ffmpeg && \
    chmod +x /usr/local/bin/ffprobe && \
    chmod +x /usr/local/bin/mp4decrypt

# 先复制依赖配置文件和源代码
# pyproject.toml: 项目配置和依赖定义
# uv.lock: 锁定的依赖版本，确保环境一致性
# gamdl: 项目源代码（uv sync 需要用到）
COPY pyproject.toml uv.lock ./
COPY gamdl ./gamdl

# 使用 uv sync 安装项目依赖和项目本身
# --frozen: 使用锁定的依赖版本，不更新 uv.lock
# --no-dev: 不安装开发依赖，减小镜像大小
RUN uv sync --frozen --no-dev

# 验证 gamdl CLI 是否安装成功
# 这一步可以在构建时发现问题，避免运行时错误
RUN uv run gamdl --help

# 创建必要的目录
# /config: 存放配置文件（如 cookies.txt）和数据库（tasks.db）
# /media/downloads: 存放下载的媒体文件
RUN mkdir -p /config /media/downloads

# 设置环境变量
# PATH: 将 uv 创建的虚拟环境添加到系统路径，使 gamdl 命令可用
# GAMDL_CONFIG_PATH: 配置文件和数据库存放路径
# GAMDL_MEDIA_PATH: 媒体文件下载路径
ENV PATH="/app/.venv/bin:$PATH" \
    GAMDL_CONFIG_PATH=/config \
    GAMDL_MEDIA_PATH=/media

# 暴露 Flask Web 应用端口
# Flask app 运行在 5800 端口
EXPOSE 5800

# 健康检查
# 每 30 秒检查一次 Web 服务是否正常响应
# 超时时间 3 秒，如果失败则容器状态变为 unhealthy
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5800/')" || exit 1

# 容器启动时执行的命令
# 运行 Flask Web 应用，提供 Web 界面和 API
CMD ["python", "gamdl/app.py"]