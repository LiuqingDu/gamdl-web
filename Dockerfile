# --- 阶段 1: 编译 Bento4 (mp4decrypt) ---
FROM python:3.11-slim AS bento4-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    cmake \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/axiomatic-systems/Bento4.git /tmp/bento4 && \
    cd /tmp/bento4 && \
    mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release .. && \
    make mp4decrypt && \
    cp mp4decrypt /usr/local/bin/

# --- 阶段 2: 编译 GPAC (MP4Box) ---
FROM python:3.11-slim AS gpac-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    pkg-config \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/gpac/gpac.git /tmp/gpac && \
    cd /tmp/gpac && \
    ./configure --static-bin && \
    make -j$(nproc) && \
    cp bin/gcc/MP4Box /usr/local/bin/

# --- 阶段 3: 最终运行镜像 ---
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装运行时系统依赖
# ffmpeg: 媒体格式转换工具
# curl/jq: 用于下载 N_m3u8DL-RE
# libicu: N_m3u8DL-RE 的依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    jq \
    ca-certificates \
    libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# 从编译阶段复制二进制文件
COPY --from=bento4-builder /usr/local/bin/mp4decrypt /usr/local/bin/
COPY --from=gpac-builder /usr/local/bin/MP4Box /usr/local/bin/

# 下载 N_m3u8DL-RE (支持多架构)
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then \
        N_M3U8_ARCH="linux-x64"; \
    elif [ "$ARCH" = "arm64" ]; then \
        N_M3U8_ARCH="linux-arm64"; \
    else \
        echo "不支持的架构: $ARCH" && exit 1; \
    fi && \
    DOWNLOAD_URL=$(curl -s https://api.github.com/repos/nilaoda/N_m3u8DL-RE/releases/latest | jq -r ".assets[] | select(.name | contains(\"${N_M3U8_ARCH}\") and (contains(\"musl\") | not)) | .browser_download_url") && \
    curl -L "$DOWNLOAD_URL" -o /tmp/nm3u8.tar.gz && \
    tar -xzf /tmp/nm3u8.tar.gz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/N_m3u8DL-RE && \
    rm /tmp/nm3u8.tar.gz

# 从官方镜像复制 uv 包管理器
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 复制项目依赖配置文件和源代码
COPY pyproject.toml uv.lock README.md ./
COPY gamdl ./gamdl
COPY web ./web

# 使用 uv sync 安装项目依赖
RUN uv sync --frozen --no-dev

# 设置环境变量
ENV PATH="/app/.venv/bin:$PATH" \
    GAMDL_CONFIG_PATH=/config \
    GAMDL_DOWNLOADS_PATH=/downloads \
    PYTHONUNBUFFERED=1

# 创建必要的目录
RUN mkdir -p /config /downloads

# 暴露 Web 应用端口
EXPOSE 5800

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5800/api/health')" || exit 1

# 容器启动命令
CMD ["python", "-m", "web.main"]
