# 使用官方 Python 3.11 精简版作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
# ffmpeg: 媒体格式转换工具
# wget/curl: 下载工具
# unzip: 解压工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 下载并安装 mp4decrypt (Bento4)
RUN wget -q https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip \
    && unzip Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip \
    && mv Bento4-SDK-1-6-0-641.x86_64-unknown-linux/bin/mp4decrypt /usr/local/bin/ \
    && chmod +x /usr/local/bin/mp4decrypt \
    && rm -rf Bento4-SDK-1-6-0-641.x86_64-unknown-linux* \
    && apt-get purge -y wget \
    && apt-get autoremove -y

# 从官方镜像复制 uv 包管理器
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 复制依赖配置文件和源代码
COPY pyproject.toml uv.lock README.md ./
COPY gamdl ./gamdl
COPY web ./web

# 使用 uv sync 安装项目依赖
RUN uv sync --frozen --no-dev

# 验证 gamdl CLI 是否安装成功
RUN uv run gamdl --help

# 创建必要的目录
RUN mkdir -p /config /downloads

# 设置环境变量
ENV PATH="/app/.venv/bin:$PATH" \
    GAMDL_CONFIG_PATH=/config \
    GAMDL_DOWNLOADS_PATH=/downloads \
    PYTHONUNBUFFERED=1

# 暴露 Web 应用端口
EXPOSE 5800

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5800/api/health')" || exit 1

# 容器启动命令
CMD ["python", "-m", "web.main"]
