# Gamdl Web (Apple Music Downloader)

基于 [Gamdl](https://github.com/glomatico/gamdl) 的 Web 版本，提供简洁的 Web 界面进行 Apple Music 歌曲下载。

## ✨ 功能特性

- 🎵 **高质量音乐下载** - 支持 AAC 256kbps 等多种编码格式
- 🌐 **Web 界面** - 简洁现代的 Web 管理界面
- 📋 **任务管理** - 串行下载队列，支持任务的创建、取消、重启、删除
- 🌍 **多语言支持** - 支持中文和英文元数据
- 🐳 **Docker 部署** - 开箱即用的容器化部署方案
- 🔄 **自动恢复** - 程序重启后自动继续未完成的任务

## 📁 项目结构

```
gamdl-web/
├── gamdl/                      # 核心下载库
│   ├── api/                    # Apple Music API
│   ├── downloader/             # 下载器实现
│   ├── interface/              # 接口层
│   └── cli/                    # CLI工具
│
├── web/                        # Web应用
│   ├── main.py                 # FastAPI应用入口
│   ├── config.py               # 配置管理
│   ├── database.py             # 数据库连接
│   ├── models.py               # 数据模型
│   ├── schemas.py              # API请求/响应模型
│   ├── routers/                # API路由
│   │   ├── tasks.py            # 任务管理API
│   │   └── settings.py         # 设置API
│   ├── services/               # 服务层
│   │   └── task_queue.py       # 任务队列管理
│   └── static/                 # 前端静态文件
│       ├── index.html
│       ├── css/style.css
│       └── js/app.js
│
├── Dockerfile                  # Docker构建文件
├── docker-compose.yml          # Docker Compose配置
└── pyproject.toml              # 项目配置
```

## 🚀 快速开始

### Docker 部署（推荐）

1. **克隆项目**

```bash
git clone https://github.com/LiuqingDu/gamdl-web.git
cd gamdl-web
```

2. **准备配置目录**

```bash
mkdir -p config downloads
```

3. **准备 Cookies 文件**

将你的 Apple Music cookies 文件放到 `config/cookies.txt`，或者启动后通过 Web 界面设置。

获取 Cookies 的方法：
- **Firefox**: [Export Cookies](https://addons.mozilla.org/addon/export-cookies-txt)
- **Chromium**: [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)

4. **启动服务**

```bash
docker-compose up -d
```

5. **访问 Web 界面**

打开浏览器访问 http://localhost:5800

### 本地开发

1. **安装依赖**

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

2. **运行开发服务器**

```bash
# 设置环境变量
export GAMDL_CONFIG_PATH=./config
export GAMDL_DOWNLOADS_PATH=./downloads

# 启动服务
python -m web.main
```

## 📖 使用说明

### Web 界面

1. **添加任务**：在输入框中粘贴 Apple Music 链接，选择语言，点击"下载"
2. **管理任务**：
   - 等待中的任务可以取消
   - 完成/错误/已取消的任务可以重启或删除
   - 任何任务都可以修改语言
   - 点击"商店"按钮可以在新窗口打开 Apple Music 页面
3. **设置**：点击右上角齿轮图标，可以配置 Cookies

### 支持的链接类型

- 歌手页面 (Artist)
- 专辑 (Album)
- 播放列表 (Playlist)
- 单曲 (Song)
- MV (Music Video)

### 任务状态说明

| 状态 | 说明 |
|------|------|
| 等待中 | 任务已加入队列，等待下载 |
| 下载中 | 正在下载中 |
| 完成 | 下载成功 |
| 错误 | 下载失败 |
| 已取消 | 用户手动取消 |

## ⚙️ 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GAMDL_CONFIG_PATH` | `/config` | 配置文件和数据库目录 |
| `GAMDL_DOWNLOADS_PATH` | `/downloads` | 下载文件保存目录 |
| `GAMDL_HOST` | `0.0.0.0` | 服务监听地址 |
| `GAMDL_PORT` | `5800` | 服务监听端口 |

### Docker 卷挂载

| 容器路径 | 说明 |
|----------|------|
| `/config` | 配置目录，包含 `cookies.txt` 和 `tasks.db` |
| `/downloads` | 下载文件保存目录 |

## 🔧 API 接口

服务启动后可以访问 http://localhost:5800/docs 查看完整的 API 文档。

### 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tasks` | 获取所有任务列表 |
| POST | `/api/tasks` | 创建新任务 |
| DELETE | `/api/tasks/{id}` | 删除任务 |
| POST | `/api/tasks/{id}/restart` | 重启任务 |
| POST | `/api/tasks/{id}/cancel` | 取消任务 |
| PATCH | `/api/tasks/{id}/language` | 修改任务语言 |
| POST | `/api/tasks/reset-all` | 重置所有任务 |
| GET | `/api/settings/cookies` | 获取 Cookies 状态 |
| POST | `/api/settings/cookies` | 更新 Cookies |
| GET | `/api/health` | 健康检查 |

## 🐳 Docker 构建

### 手动构建

```bash
docker build -t gamdl-web:latest .
```

### GitHub Actions

项目配置了 GitHub Actions 自动构建，当推送版本标签时会自动构建并推送到 Docker Hub：

```bash
git tag v1.0.0
git push origin v1.0.0
```

需要在 GitHub 仓库设置中配置以下 Secrets：
- `DOCKERHUB_USERNAME`: Docker Hub 用户名
- `DOCKERHUB_TOKEN`: Docker Hub 访问令牌

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [Gamdl](https://github.com/glomatico/gamdl) - 核心下载功能
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
- [SQLModel](https://sqlmodel.tiangolo.com/) - 数据库 ORM
