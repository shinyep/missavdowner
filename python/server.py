"""
Flask HTTP 服务器
提供 API 接口供 Electron 调用
"""
import asyncio
import json
import os
import shutil
import threading
import uuid
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

from crawler import crawler, downloader

app = Flask(__name__)
CORS(app)

# 下载任务存储
download_tasks: dict[str, dict] = {}

# 历史记录文件 - 使用用户主目录下的 .missav 目录
def get_history_file():
    """获取历史记录文件路径"""
    # 优先使用环境变量指定的路径
    history_dir = os.environ.get('MISSAV_HISTORY_DIR')
    if history_dir:
        history_path = Path(history_dir)
    else:
        # 使用用户主目录
        history_path = Path.home() / '.missav'
    history_path.mkdir(parents=True, exist_ok=True)
    return history_path / 'history.json'

HISTORY_FILE = None  # 延迟初始化


def load_history() -> list[dict]:
    """加载历史记录"""
    global HISTORY_FILE
    if HISTORY_FILE is None:
        HISTORY_FILE = get_history_file()
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []


def save_history(records: list[dict]):
    """保存历史记录"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# 运行异步函数的辅助函数
def run_async(coro):
    """在新线程中运行异步函数"""
    loop = asyncio.new_event_loop()
    result = None
    exception = None

    def _run():
        nonlocal result, exception
        try:
            result = loop.run_until_complete(coro)
        except Exception as e:
            exception = e
        finally:
            loop.close()

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join()

    if exception:
        raise exception
    return result


@app.route('/api/parse', methods=['POST'])
def parse_video():
    """解析视频信息"""
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        result = run_async(crawler.parse_video(url))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download', methods=['POST'])
def start_download():
    """开始下载视频（仅下载到本地）"""
    data = request.get_json()
    url = data.get('url')
    output_dir = data.get('outputDir', '')
    max_concurrent = data.get('maxConcurrent', 10)
    proxy = data.get('proxy', '')
    auto_merge = data.get('autoMerge', True)
    keep_temp = data.get('keepTempFiles', False)

    # 应用设置
    downloader.set_concurrent(max_concurrent)
    downloader.set_proxy(proxy if proxy else None)

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        # 先解析视频信息
        video_info = run_async(crawler.parse_video(url))

        if not video_info.get('m3u8_url'):
            return jsonify({'error': '无法获取视频下载链接'}), 400

        # 生成任务 ID
        task_id = str(uuid.uuid4())[:8]

        # 生成文件名
        safe_title = "".join(c for c in video_info['title'] if c.isalnum() or c in ' _-').strip()[:50]
        filename = f"{video_info.get('code', '') or safe_title}.mp4"
        output_path = os.path.join(output_dir, filename)

        # 存储任务信息
        download_tasks[task_id] = {
            'id': task_id,
            'url': url,
            'video_info': video_info,
            'filename': filename,
            'output_path': output_path,
            'status': 'downloading',
            'progress': 0,
            'speed': '0 MB/s',
        }

        # 在后台线程中开始下载
        def download_thread():
            try:
                def progress_callback(progress, speed):
                    download_tasks[task_id]['progress'] = progress
                    download_tasks[task_id]['speed'] = speed

                result = run_async(downloader.download_video(
                    video_info['m3u8_url'],
                    url,
                    output_path,
                    progress_callback,
                    auto_merge=auto_merge,
                    keep_temp_files=keep_temp
                ))

                download_tasks[task_id]['status'] = 'completed'
                download_tasks[task_id]['progress'] = 100

                # 保存到历史记录
                history = load_history()
                history.insert(0, {
                    'id': task_id,
                    'title': video_info['title'],
                    'filename': filename,
                    'cover': video_info.get('cover', ''),
                    'actresses': video_info.get('actresses', []),
                    'tags': video_info.get('tags', []),
                    'code': video_info.get('code', ''),
                    'outputPath': output_path,
                    'fileSize': f"{os.path.getsize(output_path) / (1024*1024):.1f} MB" if os.path.exists(output_path) else '',
                    'downloadedAt': int(datetime.now().timestamp() * 1000),
                    'downloadMode': 'local'
                })
                save_history(history)

            except Exception as e:
                download_tasks[task_id]['status'] = 'error'
                download_tasks[task_id]['error'] = str(e)
                print(f"下载失败: {e}")

        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()

        return jsonify({
            'task_id': task_id,
            'filename': filename,
            'status': 'downloading'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download-and-import', methods=['POST'])
def download_and_import():
    """下载视频并入库到 novel 项目"""
    data = request.get_json()
    url = data.get('url')
    max_concurrent = data.get('maxConcurrent', 10)
    proxy = data.get('proxy', '')
    auto_merge = data.get('autoMerge', True)
    keep_temp = data.get('keepTempFiles', False)
    novel_project_path = data.get('novelProjectPath', '')
    novel_backend_url = data.get('novelBackendUrl', 'http://127.0.0.1:8002')

    # 应用设置
    downloader.set_concurrent(max_concurrent)
    downloader.set_proxy(proxy if proxy else None)

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    if not novel_project_path:
        return jsonify({'error': 'Novel 项目路径未配置'}), 400

    # 验证 novel 项目路径存在
    manage_py_check = os.path.join(novel_project_path, 'backend', 'manage.py')
    if not os.path.exists(manage_py_check):
        return jsonify({'error': f'Novel 项目路径无效，未找到 manage.py: {manage_py_check}'}), 400

    try:
        # 先解析视频信息
        video_info = run_async(crawler.parse_video(url))

        if not video_info.get('m3u8_url'):
            return jsonify({'error': '无法获取视频下载链接'}), 400

        # 生成任务 ID
        task_id = str(uuid.uuid4())[:8]

        # 生成文件名
        safe_title = "".join(c for c in video_info['title'] if c.isalnum() or c in ' _-').strip()[:50]
        filename = f"{video_info.get('code', '') or safe_title}.mp4"

        # 存储任务信息
        download_tasks[task_id] = {
            'id': task_id,
            'url': url,
            'video_info': video_info,
            'filename': filename,
            'status': 'downloading',
            'progress': 0,
            'speed': '准备中',
        }

        # 在后台线程中下载并入库
        def download_and_import_thread():
            output_path = None
            try:
                import subprocess
                novel_python = os.path.join(novel_project_path, "backend", "venv", "Scripts", "python.exe")
                if not os.path.exists(novel_python):
                    novel_python = "python"

                backend_dir = os.path.join(novel_project_path, "backend")
                gallery_title = video_info.get("code") or safe_title
                cover_url = video_info.get("cover", "")

                # 直接下载到 novel 项目的 temp_videos 目录
                novel_temp_dir = os.path.join(novel_project_path, "img", "temp_videos")
                os.makedirs(novel_temp_dir, exist_ok=True)
                dest_filename = "missav_" + safe_title.replace(" ", "_").lower() + ".mp4"
                output_path = os.path.join(novel_temp_dir, dest_filename)

                download_tasks[task_id]["status"] = "downloading"
                download_tasks[task_id]["speed"] = "下载中"

                def progress_callback(progress, speed):
                    download_tasks[task_id]["progress"] = progress * 0.8
                    download_tasks[task_id]["speed"] = speed

                run_async(downloader.download_video(video_info["m3u8_url"], url, output_path, progress_callback, auto_merge=auto_merge, keep_temp_files=keep_temp))

                download_tasks[task_id]["progress"] = 80
                download_tasks[task_id]["speed"] = "下载完成，准备入库..."
                download_tasks[task_id]["status"] = "merging"
                download_tasks[task_id]["progress"] = 85
                download_tasks[task_id]["speed"] = "正在入库到数据库..."

                dest_path = output_path

                download_tasks[task_id]['progress'] = 90

                # 通过 Django ORM 直接入库
                # 使用 subprocess 调用 manage.py runscript 或内联脚本
                import_script = f'''
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'novel_project.settings')
sys.path.insert(0, r'{backend_dir}')
django.setup()

from api.models import Gallery, GalleryVideo
from django.core.files import File

gallery_title = {repr(gallery_title)}
video_path = r'{dest_path}'
cover_url = {repr(cover_url)}
source_url = {repr(url)}
actresses = {repr(video_info.get('actresses', []))}
tags = {repr(video_info.get('tags', []))}
code = {repr(video_info.get('code', ''))}

# 获取或创建图集
gallery, created = Gallery.objects.get_or_create(
    title=gallery_title,
    defaults={{'cover_image': None}}
)
if created:
    print(f"创建新图集: {{gallery_title}} (ID: {{gallery.id}})")
else:
    print(f"图集已存在: {{gallery_title}} (ID: {{gallery.id}})")

# 检查视频是否已存在
caption = f"missav_{{code.replace('-', '_').lower() if code else gallery_title}}.mp4"
existing = GalleryVideo.objects.filter(gallery=gallery, caption=caption).exists()
if existing:
    print(f"视频已存在，跳过: {{caption}}")
else:
    # 创建视频记录
    with open(video_path, 'rb') as f:
        django_file = File(f, name=caption)
        video = GalleryVideo.objects.create(
            gallery=gallery,
            video_file=django_file,
            caption=caption,
            order=gallery.videos.count()
        )
    print(f"视频入库成功: {{caption}} (GalleryVideo ID: {{video.id}})")

    # 触发后处理（缩略图 + HLS）
    # 通过 subprocess 调用 process_videos 命令
    import subprocess
    manage_py_file = os.path.join(backend_dir, 'manage.py')
    subprocess.Popen(
        [novel_python, manage_py_file, 'process_videos', '--video_id', str(video.id)],
        cwd=backend_dir,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    print(f"已触发视频后处理")

print(f"GALLERY_ID={{gallery.id}}")
'''

                print(f"[入库] 执行入库脚本...")
                result = subprocess.run(
                    [novel_python, '-c', import_script],
                    cwd=backend_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    encoding='utf-8',
                    errors='ignore'
                )

                print(f"[入库] stdout: {result.stdout}")
                if result.stderr:
                    print(f"[入库] stderr: {result.stderr}")

                if result.returncode != 0:
                    raise RuntimeError(f"入库脚本执行失败: {result.stderr}")

                # 解析 gallery_id
                gallery_id = None
                for line in result.stdout.splitlines():
                    if line.startswith('GALLERY_ID='):
                        gallery_id = int(line.split('=')[1])
                        break

                download_tasks[task_id]['status'] = 'completed'
                download_tasks[task_id]['progress'] = 100
                download_tasks[task_id]['speed'] = '入库完成'
                download_tasks[task_id]['galleryId'] = gallery_id

                # 保存到历史记录
                history = load_history()
                history.insert(0, {
                    'id': task_id,
                    'title': video_info['title'],
                    'filename': filename,
                    'cover': video_info.get('cover', ''),
                    'actresses': video_info.get('actresses', []),
                    'tags': video_info.get('tags', []),
                    'code': video_info.get('code', ''),
                    'outputPath': f"novel://gallery/{gallery_id}" if gallery_id else '',
                    'fileSize': f"{os.path.getsize(output_path) / (1024*1024):.1f} MB" if os.path.exists(output_path) else '',
                    'downloadedAt': int(datetime.now().timestamp() * 1000),
                    'downloadMode': 'novel'
                })
                save_history(history)

            except Exception as e:
                download_tasks[task_id]['status'] = 'error'
                download_tasks[task_id]['error'] = str(e)
                print(f"[入库] 失败: {e}")
            finally:
                # 清理临时文件
                pass  # 入库模式下文件已直接保存在 novel 项目目录，无需清理

        thread = threading.Thread(target=download_and_import_thread, daemon=True)
        thread.start()

        return jsonify({
            'task_id': task_id,
            'filename': filename,
            'status': 'downloading'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/progress/<task_id>')
def get_progress(task_id: str):
    """获取下载进度"""
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    return jsonify({
        'taskId': task_id,
        'progress': task['progress'],
        'speed': task['speed'],
        'status': task['status'],
        'error': task.get('error'),
        'galleryId': task.get('galleryId')
    })


@app.route('/api/pause/<task_id>', methods=['POST'])
def pause_download(task_id: str):
    """暂停下载"""
    downloader.pause_task(task_id)
    if task_id in download_tasks:
        download_tasks[task_id]['status'] = 'paused'
    return jsonify({'success': True})


@app.route('/api/resume/<task_id>', methods=['POST'])
def resume_download(task_id: str):
    """恢复下载"""
    downloader.resume_task(task_id)
    if task_id in download_tasks:
        download_tasks[task_id]['status'] = 'downloading'
    return jsonify({'success': True})


@app.route('/api/history')
def get_history():
    """获取历史记录"""
    records = load_history()
    return jsonify({'records': records})


@app.route('/api/history/<record_id>', methods=['DELETE'])
def delete_history(record_id: str):
    """删除历史记录"""
    history = load_history()
    history = [r for r in history if r['id'] != record_id]
    save_history(history)
    return jsonify({'success': True})


@app.route('/api/history', methods=['DELETE'])
def clear_history():
    """清空历史记录"""
    save_history([])
    return jsonify({'success': True})


@app.route('/health')
def health():
    """健康检查"""
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=15678)
    args = parser.parse_args()

    print(f"Starting server on port {args.port}")
    app.run(host='127.0.0.1', port=args.port, debug=False)






