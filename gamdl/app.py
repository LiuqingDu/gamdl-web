import re
import sqlite3
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, render_template
from pathlib import Path
import os

# Get base paths from environment variables or use defaults
CONFIG_PATH = Path('/config')
COOKIES_PATH = CONFIG_PATH / "cookies.txt"
if not COOKIES_PATH.exists():
    print("\033[91mError: Cookies file not found at {}\033[0m".format(COOKIES_PATH))
    exit(1)

MEDIA_PATH = Path('/media')
DOWNLOADS_PATH = MEDIA_PATH / "downloads"
# Create necessary directories
DOWNLOADS_PATH.mkdir(parents=True, exist_ok=True)
if not MEDIA_PATH.exists():
    print("\033[91mError: Media directory not found at {}\033[0m".format(MEDIA_PATH))
    exit(1)

app = Flask(__name__)

# Limit to 1 worker to ensure sequential processing
executor = ThreadPoolExecutor(max_workers=1)

# Regular expression to extract task ID and artist name from URL
VALID_URL_RE = re.compile(r"/([a-z]{2})/(artist|album|playlist|song|music-video|post)/([^/]*)(?:/([^/?]*))?(?:\?i=)?([0-9a-z]*)?")

# Add global variable for last command output
last_command_output = None

def extract_artist_name(url):
    match = VALID_URL_RE.search(url)
    return match.group(3) if match else None

def extract_artist_id(url):
    match = VALID_URL_RE.search(url)
    return match.group(4) if match else None

def get_db_connection():
    """Create and return a database connection"""
    db_path = CONFIG_PATH / "tasks.db"

    return sqlite3.connect(db_path)

def execute_db_query(query, params=None, fetch_one=False):
    """Execute a database query and handle connection management"""
    conn = get_db_connection()
    try:
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
    finally:
        conn.close()

def init_db():
    query = '''CREATE TABLE IF NOT EXISTS tasks
             (artist_id TEXT PRIMARY KEY, url TEXT, status INTEGER, language TEXT)'''
    execute_db_query(query)

def save_task(artist_id, url, language, status=0):
    query = 'INSERT OR REPLACE INTO tasks (artist_id, url, status, language) VALUES (?, ?, ?, ?)'
    execute_db_query(query, (artist_id, url, status, language))

def get_pending_task():
    query = 'SELECT artist_id, url, language FROM tasks WHERE status = 0 LIMIT 1'
    return execute_db_query(query, fetch_one=True)

def get_task(artist_id):
    """Get task by artist_id"""
    query = 'SELECT url, status, language FROM tasks WHERE artist_id = ?'
    return execute_db_query(query, (artist_id,), fetch_one=True)

def process_pending_task():
    task = get_pending_task()
    if not task:
        return
        
    # task is a tuple of (artist_id, url, language)
    artist_id, url, language = task
    
    try:
        # Prepare download command
        output_path = DOWNLOADS_PATH
        cookies_path = COOKIES_PATH
        temp_path = Path(f"t{artist_id}")
            
        comm = f'gamdl "{url}" -l {language} -o {output_path} --temp-path {temp_path} -c {cookies_path}'
        
        # Submit download task to thread pool
        executor.submit(download_process, artist_id, url, language, comm)
        
    except Exception as e:
        # Mark as error if setup fails
        save_task(artist_id, url, language, -1)

def download_process(artist_id, url, language, comm):
    global last_command_output
    try:
        # Update status to downloading
        save_task(artist_id, url, language, 1)
        
        process = subprocess.Popen(comm, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        # Read output line by line
        for line in process.stdout:
            line = line.strip()
            last_command_output = line
            
        process.wait()
        status = 2 if process.returncode == 0 else -1
        save_task(artist_id, url, language, status)
        
    except Exception as e:
        save_task(artist_id, url, language, -1)
    finally:
        # Clean up last_command_output when task finishes
        last_command_output = None
    
    process_pending_task()

@app.route('/run')
def run_task():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    artist_id = extract_artist_id(url)
    if not artist_id:
        return jsonify({'error': 'Invalid URL'}), 400

    language = request.args.get('language', 'zh-CN')
    save_task(artist_id, url, language)
    process_pending_task()

    return jsonify({'artist_id': artist_id}), 200

@app.route('/status')
def status():
    try:
        tasks = execute_db_query('SELECT artist_id, url, status FROM tasks')
        
        status_map = {
            0: 'Pending',
            1: 'Downloading', 
            2: 'Success',
            -1: 'Error',
            -2: 'Stopped'
        }
        
        formatted_tasks = [{
            'artist_id': task[0],
            'artist_name': extract_artist_name(task[1]),
            'status': status_map.get(task[2], 'Unknown')
        } for task in tasks]
        
        return jsonify({
            'tasks': formatted_tasks,
            'log': last_command_output
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stop/<artist_id>', methods=['POST'])
def stop_task(artist_id):
    task = get_task(artist_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
        
    url, status, language = task
    if status not in [0]:
        return jsonify({'error': 'Task is not pending'}), 400
        
    save_task(artist_id, url, language, -2)
    return jsonify({'status': 'stopped'}), 200

@app.route('/restart/<artist_id>', methods=['POST'])
def restart_task(artist_id):
    task = get_task(artist_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
        
    url, status, language = task
    if status not in [-1, -2, 2]:
        return jsonify({'error': 'Task cannot be restarted'}), 400
        
    save_task(artist_id, url, language, 0)
    process_pending_task()
    return jsonify({'status': 'restarted'}), 200

@app.route('/')
def index():
    return render_template("index.html")

if __name__ == '__main__':
    # Initialize database and create tables
    init_db()
    # Reset any unfinished tasks (downloading) to pending state
    execute_db_query('UPDATE tasks SET status = 0 WHERE status = 1')
    process_pending_task()
    app.run(host='0.0.0.0', port=5800)
