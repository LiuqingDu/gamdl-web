import re
import subprocess
import threading
from flask import Flask, request, jsonify, render_template
from pathlib import Path

app = Flask(__name__)

# Storage for task information
task_info = {}

# Storage for task processes
task_processes = {}

# Regular expression to extract task ID and artist name
VALID_URL_RE = re.compile(r"/([a-z]{2})/(artist|album|playlist|song|music-video|post)/([^/]*)(?:/([^/?]*))?(?:\?i=)?([0-9a-z]*)?")

def extract_artist_name(url):
    match = VALID_URL_RE.search(url)
    return match.group(3) if match else None

def extract_artist_id(url):
    match = VALID_URL_RE.search(url)
    return match.group(4) if match else None

def download_process(artist_id, comm):
    try:
        task_info[artist_id]['status'] = 'Downloading'
        task_processes[artist_id] = subprocess.Popen(comm, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        for line in task_processes[artist_id].stdout:
            task_info[artist_id]['output'] = line
            if task_info[artist_id]['status'] == 'Stopped':
                task_processes[artist_id].terminate()
                break
        task_processes[artist_id].wait()
        if task_processes[artist_id].returncode == 0 and task_info[artist_id]['status'] != 'Stopped':
            task_info[artist_id]['status'] = 'Completed'
        elif task_info[artist_id]['status'] != 'Stopped':
            task_info[artist_id]['status'] = 'Failed'
    except Exception as e:
        task_info[artist_id]['status'] = 'Failed'
        task_info[artist_id]['output'] = str(e)
    finally:
        if artist_id in task_processes:
            del task_processes[artist_id]

@app.route('/run')
def run_task():
    url = request.args.get('url')
    language = request.args.get('language', 'zh-CN')  # Default language is zh-CN
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    output_path = Path("/media/downloads")

    artist_id = extract_artist_id(url)
    if not artist_id:
        return jsonify({'error': 'Invalid URL'}), 400

    artist_name = extract_artist_name(url)

    cookies_path = Path("/config/cookies.txt")

    temp_path = Path(f"t{artist_id}")
    
    task_info[artist_id] = {
        'artist_id': artist_id,
        'artist': artist_name or 'Unknown',
        'status': 'Pending',
        'output': ''
    }

    comm = f'gamdl "{url}" -l {language} -o {output_path} --temp-path {temp_path} -c {cookies_path}'

    # Start the download process in a separate thread
    thread = threading.Thread(target=download_process, args=(artist_id, comm))
    thread.start()

    return jsonify({'artist_id': artist_id}), 200

@app.route('/status')
def status():
    return jsonify(task_info)

@app.route('/stop/<artist_id>', methods=['POST'])
def stop_task(artist_id):
    if artist_id in task_info:
        if task_info[artist_id]['status'] == 'Downloading':
            task_info[artist_id]['status'] = 'Stopped'
            if artist_id in task_processes:
                task_processes[artist_id].terminate()
        return jsonify({'status': 'stopped'}), 200
    return jsonify({'error': 'Task not found'}), 404

@app.route('/')
def index():
    return render_template("index.html")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5800)
