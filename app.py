import re
import threading
from flask import Flask, request, jsonify, render_template
from pathlib import Path
from gamdl.cli import main

app = Flask(__name__)

# Storage for tasks and threads
tasks = {}
threads = {}

# Regular expression to extract task ID and artist name
VALID_URL_RE = re.compile(r"/([a-z]{2})/(artist|album|playlist|song|music-video|post)/([^/]*)(?:/([^/?]*))?(?:\?i=)?([0-9a-z]*)?")

def extract_storefront(url):
    match = VALID_URL_RE.search(url)
    return match.group(1) if match else None

def extract_artist_name(url):
    match = VALID_URL_RE.search(url)
    return match.group(3) if match else None

def extract_artist_id(url):
    match = VALID_URL_RE.search(url)
    return match.group(4) if match else None

@app.route('/run')
def run_task():
    url = request.args.get('url')
    language = request.args.get('language', 'zh-CN')  # Default language is zh-CN
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    output_path = Path("./downloads")

    artist_id = extract_artist_id(url)

    artist_name = extract_artist_name(url)

    storefront = extract_storefront(url)

    if storefront == 'cn':
        cookies_path = Path("./cookies/cookies_cn.txt")
    else:
        cookies_path = Path("./cookies/cookies_us.txt")

    temp_path = Path(f"t{artist_id}")
    
    tasks[artist_id] = {
        'artist': artist_name or 'Unknown',
        'status': 'Pending',
        'output': ''
    }

    # Start the download process in a separate thread
    def download_thread():
        try:
            tasks[artist_id]['status'] = 'Downloading'
            main(urls=[url], language=language, output_path=output_path, temp_path=temp_path, cookies_path=cookies_path, storefront=storefront)
            tasks[artist_id]['status'] = 'Completed'
        except Exception as e:
            tasks[artist_id]['status'] = 'Failed'
            tasks[artist_id]['output'] = str(e)

    thread = threading.Thread(target=download_thread)
    thread.start()
    
    # Save thread information
    threads[artist_id] = thread

    return jsonify({'task_id': artist_id}), 200

@app.route('/status')
def status():
    return jsonify(tasks)

@app.route('/stop/<task_id>', methods=['POST'])
def stop_task(task_id):
    thread = threads.get(task_id)
    if thread:
        # Set a flag in the task to indicate it should stop
        tasks[task_id]['status'] = 'Stopping'
        # Wait for the thread to finish (you might want to add a timeout here)
        thread.join(timeout=5)
        tasks[task_id]['status'] = 'Stopped'
        tasks[task_id]['output'] = tasks[task_id]['output'] or 'Task was stopped manually.'
        # Remove the thread from our tracking
        del threads[task_id]
        return jsonify({'status': 'stopped'}), 200
    return jsonify({'error': 'Task not found'}), 404

@app.route('/')
def index():
    return render_template("index.html")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5800)
