import re
import sqlite3
import subprocess
import sys
import logging
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, render_template
from pathlib import Path
import os
from contextlib import contextmanager
import threading

# 配置日志输出到标准输出，这样Docker可以看到
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 从环境变量获取基础路径或使用默认值
CONFIG_PATH = Path(os.getenv('GAMDL_CONFIG_PATH', '/config'))
# 创建必要的目录
CONFIG_PATH.mkdir(parents=True, exist_ok=True)
DOWNLOADS_PATH = Path(os.getenv('GAMDL_DOWNLOADS_PATH', '/downloads'))
# 创建必要的目录
DOWNLOADS_PATH.mkdir(parents=True, exist_ok=True)
COOKIES_PATH = CONFIG_PATH / "cookies.txt"
if not COOKIES_PATH.exists():
    logger.error(f"错误: 在 {COOKIES_PATH} 找不到cookies文件")
    sys.exit(1)

logger.info(f"配置路径: {CONFIG_PATH}")
logger.info(f"下载路径: {DOWNLOADS_PATH}")
logger.info(f"Cookies路径: {COOKIES_PATH}")

app = Flask(__name__)

# 限制为1个工作线程以确保顺序处理
executor = ThreadPoolExecutor(max_workers=1)

# 用于提取任务ID和艺术家名称的正则表达式
VALID_URL_RE = re.compile(r"/([a-z]{2})/(artist|album|playlist|song|music-video|post)/([^/]*)(?:/([^/?]*))?(?:\?i=)?([0-9a-z]*)?")

# 添加全局变量用于最后命令输出
last_command_output = None
# 应该添加线程锁
last_command_output_lock = threading.Lock()

def extract_url_parts(url):
    """
    从Apple Music URL中提取所有有用部分
    
    Args:
        url (str): Apple Music URL
        
    Returns:
        dict: 包含type, name, id的字典，如果解析失败返回None
    """
    match = VALID_URL_RE.search(url)
    if not match:
        return None
    
    url_type = match.group(2)
    name = match.group(3)
    # 处理不同的URL格式，ID可能在group(4)或group(5)
    url_id = match.group(4) if match.group(4) else match.group(5)
    
    return {
        'type': url_type,
        'name': name,
        'id': url_id
    }

def extract_url_type(url):
    """
    从URL中提取类型（artist/album/playlist等）
    
    Args:
        url (str): Apple Music URL
        
    Returns:
        str: URL类型，如果解析失败返回None
    """
    parts = extract_url_parts(url)
    return parts['type'] if parts else None

def extract_artist_name(url):
    """
    从URL中提取艺术家名称（保持原有函数兼容性）
    
    Args:
        url (str): Apple Music URL
        
    Returns:
        str: 艺术家名称，如果解析失败返回None
    """
    parts = extract_url_parts(url)
    return parts['name'] if parts else None

def extract_artist_id(url):
    """
    从URL中提取艺术家ID（保持原有函数兼容性）
    
    Args:
        url (str): Apple Music URL
        
    Returns:
        str: 艺术家ID，如果解析失败返回None
    """
    parts = extract_url_parts(url)
    return parts['id'] if parts else None

def assemble_url(url_type, name, url_id):
    """
    组装完整的Apple Music URL，使用硬编码的us国家代码
    
    Args:
        url_type (str): URL类型（artist/album/playlist等）
        name (str): 名称
        url_id (str): ID
        
    Returns:
        str: 完整的Apple Music URL
    """
    return f"https://music.apple.com/us/{url_type}/{name}/{url_id}"

@contextmanager
def get_db_connection():
    """
    创建并返回数据库连接的上下文管理器
    
    Yields:
        sqlite3.Connection: 数据库连接对象
    """
    db_path = CONFIG_PATH / "tasks.db"
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()

def execute_db_query(query, params=None, fetch_one=False):
    """
    执行数据库查询并处理连接管理
    
    Args:
        query (str): SQL查询语句
        params (tuple): 查询参数
        fetch_one (bool): 是否只获取一条记录
        
    Returns:
        list/tuple: 查询结果
    """
    with get_db_connection() as conn:
        c = conn.cursor()
        if params:
            c.execute(query, params)
        else:
            c.execute(query)
        
        if fetch_one:
            result = c.fetchone()
        else:
            result = c.fetchall()
            
        conn.commit()
        return result

def init_db():
    """
    初始化数据库表结构
    """
    query = '''CREATE TABLE IF NOT EXISTS tasks
             (artist_id TEXT PRIMARY KEY, 
              type TEXT,
              name TEXT,
              status INTEGER, 
              language TEXT)'''
    execute_db_query(query)

def save_task(artist_id, url, language, status=0):
    """
    保存任务到数据库
    
    Args:
        artist_id (str): 艺术家ID
        url (str): Apple Music URL
        language (str): 语言代码
        status (int): 任务状态
        
    Returns:
        bool: 保存是否成功
    """
    url_parts = extract_url_parts(url)
    if not url_parts:
        return False
    
    query = '''INSERT OR REPLACE INTO tasks 
               (artist_id, type, name, status, language) 
               VALUES (?, ?, ?, ?, ?)'''
    execute_db_query(query, (
        artist_id,
        url_parts['type'],
        url_parts['name'],
        status,
        language
    ))
    return True

def get_pending_task():
    """
    获取待处理任务
    
    Returns:
        tuple: (artist_id, type, name, language) 或 None
    """
    query = 'SELECT artist_id, type, name, language FROM tasks WHERE status = 0 LIMIT 1'
    return execute_db_query(query, fetch_one=True)

def get_task(artist_id):
    """
    根据artist_id获取任务
    
    Args:
        artist_id (str): 艺术家ID
        
    Returns:
        tuple: (type, name, status, language) 或 None
    """
    query = 'SELECT type, name, status, language FROM tasks WHERE artist_id = ?'
    return execute_db_query(query, (artist_id,), fetch_one=True)

def reset_all_tasks_to_pending():
    """
    将所有任务重置为等待状态，除了当前正在运行的任务
    
    Returns:
        int: 重置的任务数量
    """
    # 将所有非运行中的任务重置为等待状态
    reset_query = 'UPDATE tasks SET status = 0 WHERE status != 1'
    execute_db_query(reset_query)
    
    # 获取重置的任务数量
    count_query = 'SELECT COUNT(*) FROM tasks WHERE status = 0'
    result = execute_db_query(count_query, fetch_one=True)
    return result[0] if result else 0

def reset_tasks_to_pending_from_running():
    """
    将所有正在运行的任务重置为等待状态
    """
    reset_query = 'UPDATE tasks SET status = 0 WHERE status = 1'
    execute_db_query(reset_query)
    return

def process_pending_task():
    """
    处理待处理任务
    """
    task = get_pending_task()
    if not task:
        return
        
    # task是一个包含 (artist_id, type, name, language) 的元组
    artist_id, url_type, name, language = task
    
    try:
        # 组装完整URL
        url = assemble_url(url_type, name, artist_id)
        if not url:
            logger.error(f"无法组装URL: {url_type}/{name}/{artist_id}")
            return
            
        # 准备下载命令
        output_path = DOWNLOADS_PATH
        cookies_path = COOKIES_PATH
        temp_path = Path(f"t{artist_id}")
            
        comm = f'gamdl "{url}" -l {language} -o {output_path} --temp-path {temp_path} -c {cookies_path}'
        
        # 提交下载任务到线程池
        executor.submit(download_process, artist_id, url, language, comm)
        
    except Exception as e:
        # 如果设置失败则标记为错误
        logger.error(f"处理待处理任务时发生异常: {str(e)}")
        try:
            url = assemble_url(url_type, name, artist_id)
        except:
            url = f"https://music.apple.com/us/{url_type}/{name}/{artist_id}"
        save_task(artist_id, url, language, -1)

def download_process(artist_id, url, language, comm):
    """
    下载处理函数
    
    Args:
        artist_id (str): 艺术家ID
        url (str): Apple Music URL
        language (str): 语言代码
        comm (str): 要执行的命令
    """
    global last_command_output
    try:
        logger.info(f"开始下载任务: {artist_id}, URL: {url}, 语言: {language}")
        # 更新状态为下载中
        save_task(artist_id, url, language, 1)
        
        logger.info(f"执行命令: {comm}")
        process = subprocess.Popen(comm, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        # 逐行读取输出
        for line in process.stdout:
            line = line.strip()
            with last_command_output_lock:
                last_command_output = line
            # 同时输出到Docker日志
            logger.info(f"[{artist_id}] {line}")
            
        process.wait()
        status = 2 if process.returncode == 0 else -1
        save_task(artist_id, url, language, status)
        
        if status == 2:
            logger.info(f"任务 {artist_id} 下载成功")
        else:
            logger.error(f"任务 {artist_id} 下载失败，返回码: {process.returncode}")
        
    except Exception as e:
        logger.error(f"任务 {artist_id} 下载过程中发生异常: {str(e)}")
        save_task(artist_id, url, language, -1)
    finally:
        # 任务完成时清理last_command_output
        with last_command_output_lock:
            last_command_output = None
    
    process_pending_task()

@app.route('/run')
def run_task():
    """
    运行任务路由
    """
    url = request.args.get('url')
    if not url:
        logger.warning("收到无效请求: 缺少URL参数")
        return jsonify({'error': '需要提供URL'}), 400

    name = extract_artist_name(url)
    artist_id = extract_artist_id(url)
    if not artist_id:
        logger.warning(f"收到无效URL: {url}")
        return jsonify({'error': '无效的URL'}), 400

    language = request.args.get('language', 'zh-CN')
    logger.info(f"添加新任务: {name} (ID: {artist_id}), 语言: {language}")
    
    if save_task(artist_id, url, language):
        process_pending_task()
        return jsonify({
            'artist_id': artist_id,
            'message': f'任务已添加到队列，名称: {name}'
        }), 200
    else:
        logger.error(f"保存任务失败: {url}")
        return jsonify({'error': '无效的URL格式'}), 400

@app.route('/status')
def status():
    """
    状态查询路由
    """
    try:
        # 修改查询以包含语言信息
        tasks = execute_db_query('SELECT artist_id, type, name, status, language FROM tasks')
        
        status_map = {
            0: '等待中',
            1: '下载中', 
            2: '成功',
            -1: '错误',
            -2: '已停止'
        }
        
        # 语言映射
        language_map = {
            'zh-CN': '中文',
            'en-US': 'English',
        }
        
        formatted_tasks = [{
            'artist_id': task[0],
            'type': task[1],
            'name': task[2],
            'status': status_map.get(task[3], '未知'),
            'language': language_map.get(task[4], task[4])  # 使用映射或原始值
        } for task in tasks]
        
        # 线程安全地获取last_command_output
        with last_command_output_lock:
            current_log = last_command_output
        
        return jsonify({
            'tasks': formatted_tasks,
            'log': current_log
        })
    except Exception as e:
        logger.error(f"获取状态时发生异常: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/stop/<artist_id>', methods=['POST'])
def stop_task(artist_id):
    """
    停止任务路由
    
    Args:
        artist_id (str): 艺术家ID
    """
    logger.info(f"尝试停止任务: {artist_id}")
    task = get_task(artist_id)
    if not task:
        logger.warning(f"找不到任务: {artist_id}")
        return jsonify({'error': '找不到任务'}), 404
        
    url_type, name, status, language = task
    if status not in [0]:
        logger.warning(f"任务 {artist_id} 不在等待状态，无法停止")
        return jsonify({'error': '任务不在等待状态，无法停止'}), 400
        
    url = assemble_url(url_type, name, artist_id)
    save_task(artist_id, url, language, -2)
    logger.info(f"任务 {artist_id} ({name}) 已停止")
    return jsonify({
        'status': '已停止',
        'message': f'任务 {name} 已停止'
    }), 200

@app.route('/restart/<artist_id>', methods=['POST'])
def restart_task(artist_id):
    """
    重启任务路由
    
    Args:
        artist_id (str): 艺术家ID
    """
    logger.info(f"尝试重启任务: {artist_id}")
    task = get_task(artist_id)
    if not task:
        logger.warning(f"找不到任务: {artist_id}")
        return jsonify({'error': '找不到任务'}), 404
        
    url_type, name, status, language = task
    if status not in [-1, -2, 2]:
        logger.warning(f"任务 {artist_id} 当前状态不允许重启")
        return jsonify({'error': '任务无法重启，当前状态不允许重启'}), 400
        
    url = assemble_url(url_type, name, artist_id)
    save_task(artist_id, url, language, 0)
    process_pending_task()
    logger.info(f"任务 {artist_id} ({name}) 已重启")
    return jsonify({
        'status': '已重启',
        'message': f'任务 {name} 已重启并加入队列'
    }), 200

@app.route('/resetAllTasks', methods=['POST'])
def reset_tasks():
    """
    重置所有任务为等待状态的路由（除了正在运行的任务）
    """
    try:
        logger.info("重置所有非运行中的任务")
        count = reset_all_tasks_to_pending()
        logger.info(f"重置了 {count} 个任务")
        return jsonify({
            'status': 'success',
            'message': '所有非运行中的任务已重置为等待状态'
        }), 200
    except Exception as e:
        logger.error(f"重置任务失败: {str(e)}")
        return jsonify({'error': f'重置失败: {str(e)}'}), 500

@app.route('/updateLanguage/<artist_id>', methods=['POST'])
def update_language(artist_id):
    """
    更新任务语言的路由
    
    Args:
        artist_id (str): 艺术家ID
    """
    try:
        data = request.get_json()
        new_language = data.get('language')
        
        if not new_language:
            logger.warning(f"更新语言失败: 缺少语言参数")
            return jsonify({'error': '需要提供语言参数'}), 400
        
        # 验证语言代码的有效性
        valid_languages = ['zh-CN', 'en-US']
        if new_language not in valid_languages:
            logger.warning(f"不支持的语言代码: {new_language}")
            return jsonify({'error': f'不支持的语言代码: {new_language}'}), 400
            
        # 获取当前任务信息
        task = get_task(artist_id)
        if not task:
            logger.warning(f"找不到任务: {artist_id}")
            return jsonify({'error': '找不到任务'}), 404
            
        url_type, name, status, current_language = task
        
        # 更新语言
        url = assemble_url(url_type, name, artist_id)
        save_task(artist_id, url, new_language, status)
        
        logger.info(f"任务 {artist_id} ({name}) 语言已从 {current_language} 更新为 {new_language}")
        return jsonify({
            'status': '语言已更新',
            'message': f'任务 {name} 的语言已更新为 {new_language}'
        }), 200
        
    except Exception as e:
        logger.error(f"更新语言失败: {str(e)}")
        return jsonify({'error': f'更新失败: {str(e)}'}), 500

@app.route('/')
def index():
    """
    主页路由
    """
    return render_template("index.html")

if __name__ == '__main__':
    logger.info("启动 Apple Music 下载器服务")
    # 初始化数据库并创建表
    init_db()
    logger.info("数据库初始化完成")
    # 重置所有任务为等待状态，除了当前正在运行的任务
    reset_tasks_to_pending_from_running()
    logger.info("重置运行中的任务完成")
    process_pending_task()
    logger.info("开始处理待处理任务")
    logger.info("服务启动完成，监听端口 5800")
    app.run(host='0.0.0.0', port=5800)
