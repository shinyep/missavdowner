"""
Flask HTTP 服务器
提供 API 接口供 Electron 调用
"""
import asyncio
import json
import os
import threading
import time
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


def _phase_title(phase: str) -> str:
    """将阶段代码转为中文描述"""
    titles = {
        'download_segments': '正在下载视频片段',
        'merging': '正在合并视频',
        'importing': '正在入库到数据库',
        'transcoding': '正在重新编码',
        'cleaning': '正在清理临时文件',
    }
    return titles.get(phase, phase or '')


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
    """开始下载视频"""
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
            'phase': 'download_segments',
            'phaseTitle': _phase_title('download_segments'),
            'detail': '',
            'transcodeProgress': 0,
        }

        # 在后台线程中开始下载
        def download_thread():
            try:
                def progress_callback(progress, speed, phase=None, detail=None):
                    download_tasks[task_id]['progress'] = progress
                    download_tasks[task_id]['speed'] = speed
                    if phase:
                        download_tasks[task_id]['phase'] = phase
                        download_tasks[task_id]['phaseTitle'] = _phase_title(phase)
                    if detail:
                        download_tasks[task_id]['detail'] = detail

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
                download_tasks[task_id]['phase'] = None
                download_tasks[task_id]['phaseTitle'] = ''

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
                    'downloadedAt': int(datetime.now().timestamp() * 1000)
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
        'phase': task.get('phase'),
        'phaseTitle': task.get('phaseTitle', ''),
        'detail': task.get('detail', ''),
        'transcodeProgress': task.get('transcodeProgress', 0),
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

@app.route('/api/download-to-novel', methods=['POST'])
def download_to_novel():
    """下载视频并入库到 Novel 项目"""
    data = request.get_json()
    url = data.get('url')
    novel_project_path = data.get('novelProjectPath', 'F:\\novel')
    max_concurrent = data.get('maxConcurrent', 10)
    proxy = data.get('proxy', '')
    auto_merge = data.get('autoMerge', True)
    keep_temp = data.get('keepTempFiles', False)

    downloader.set_concurrent(max_concurrent)
    downloader.set_proxy(proxy if proxy else None)

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        video_info = run_async(crawler.parse_video(url))
        if not video_info.get('m3u8_url'):
            return jsonify({'error': '无法获取视频下载链接'}), 400

        task_id = str(uuid.uuid4())[:8]
        safe_title = "".join(c for c in video_info['title'] if c.isalnum() or c in ' _-').strip()[:50]
        filename = f"{video_info.get('code', '') or safe_title}.mp4"

        # Novel 项目路径
        novel_backend = os.path.join(novel_project_path, 'backend')
        novel_venv_python = os.path.join(novel_backend, 'venv', 'Scripts', 'python.exe')
        novel_media_root = os.path.join(novel_project_path, 'img')
        temp_dir = os.path.join(novel_media_root, 'temp_videos')
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.join(temp_dir, filename)

        download_tasks[task_id] = {
            'id': task_id,
            'url': url,
            'video_info': video_info,
            'filename': filename,
            'output_path': output_path,
            'status': 'downloading',
            'progress': 0,
            'speed': '0 MB/s',
            'downloadMode': 'novel',
            'phase': 'download_segments',
            'phaseTitle': _phase_title('download_segments'),
            'detail': f'临时目录: {temp_dir}',
            'transcodeProgress': 0,
        }

        def download_thread():
            import subprocess as _sp
            try:
                def progress_callback(progress, speed, phase=None, detail=None):
                    download_tasks[task_id]['progress'] = progress
                    download_tasks[task_id]['speed'] = speed
                    if phase:
                        download_tasks[task_id]['phase'] = phase
                        download_tasks[task_id]['phaseTitle'] = _phase_title(phase)
                    if detail:
                        download_tasks[task_id]['detail'] = detail

                # 下载视频到 Novel 的 temp_videos 目录
                run_async(downloader.download_video(
                    video_info['m3u8_url'], url, output_path, progress_callback,
                    auto_merge=auto_merge, keep_temp_files=keep_temp
                ))

                # 切换到入库阶段
                download_tasks[task_id]['phase'] = 'importing'
                download_tasks[task_id]['phaseTitle'] = _phase_title('importing')
                download_tasks[task_id]['speed'] = '入库中...'
                download_tasks[task_id]['detail'] = '正在创建 Gallery 和 GalleryVideo'
                print(f"[Novel] 下载完成，开始入库: {filename}")

                # 步骤1: 创建 Gallery + GalleryVideo
                import_script = (
                    "import os, sys\n"
                    "os.environ['DJANGO_SETTINGS_MODULE'] = 'novel_project.settings'\n"
                    "sys.path.insert(0, " + repr(novel_backend) + ")\n"
                    "import django\n"
                    "django.setup()\n"
                    "from api.models import Gallery, GalleryVideo\n"
                    "from django.core.files import File\n"
                    "video_path = " + repr(output_path) + "\n"
                    "gallery_title = " + repr(video_info['title']) + "\n"
                    "video_caption = " + repr(filename) + "\n"
                    "gallery, created = Gallery.objects.get_or_create(title=gallery_title, defaults={'cover_image': None})\n"
                    "print(f'Gallery ID: {gallery.id}, created={created}')\n"
                    "with open(video_path, 'rb') as f:\n"
                    "    django_file = File(f, name=video_caption)\n"
                    "    video = GalleryVideo.objects.create(gallery=gallery, video_file=django_file, caption=video_caption, order=0)\n"
                    "print(f'GalleryVideo ID: {video.id}')\n"
                    "print(f'VIDEO_ID={video.id}')\n"
                )

                result = _sp.run(
                    [novel_venv_python, '-c', import_script],
                    capture_output=True, text=True, timeout=120,
                    cwd=novel_backend,
                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
                )

                print(f"[Novel] import stdout: {result.stdout}")
                if result.stderr:
                    print(f"[Novel] import stderr: {result.stderr}")

                if result.returncode != 0:
                    raise Exception(f"入库脚本失败: {result.stderr}")

                video_id = None
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('VIDEO_ID='):
                        video_id = int(line.split('=', 1)[1])
                        break

                if not video_id:
                    raise Exception(f"无法解析 video_id: {result.stdout}")

                # 切换到转码阶段
                print(f"[Novel] video_id={video_id}，开始重新编码...")
                download_tasks[task_id]['phase'] = 'transcoding'
                download_tasks[task_id]['phaseTitle'] = _phase_title('transcoding')
                download_tasks[task_id]['speed'] = '转码中...'
                download_tasks[task_id]['detail'] = f'video_id={video_id}'

                # 步骤2: 使用 Popen 启动 process_videos，轮询 DB 获取进度
                encode_cmd = [novel_venv_python, 'manage.py', 'process_videos', '--video_id', str(video_id)]
                print(f"[Novel] 启动转码: {' '.join(encode_cmd)}")
                encode_proc = _sp.Popen(
                    encode_cmd,
                    stdout=_sp.DEVNULL, stderr=_sp.PIPE, text=True,
                    cwd=novel_backend,
                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
                )

                # 检查进程是否立即失败
                time.sleep(2)
                if encode_proc.poll() is not None:
                    _, early_err = encode_proc.communicate(timeout=5)
                    raise Exception(f"process_videos 启动失败: {early_err}")

                # 轮询数据库进度
                # 初始进度更新
                download_tasks[task_id]['detail'] = '转码进程已启动，等待处理...'
                poll_script = (
                    "import os, sys\n"
                    "os.environ['DJANGO_SETTINGS_MODULE'] = 'novel_project.settings'\n"
                    "sys.path.insert(0, " + repr(novel_backend) + ")\n"
                    "import django\n"
                    "django.setup()\n"
                    "from api.models import GalleryVideo\n"
                    f"v = GalleryVideo.objects.get(id={video_id})\n"
                    "print(f'PROGRESS={v.progress}')\n"
                    "print(f'STATUS={v.status}')\n"
                )

                prev_progress = 0
                while encode_proc.poll() is None:
                    try:
                        poll_result = _sp.run(
                            [novel_venv_python, '-c', poll_script],
                            capture_output=True, text=True, timeout=5,
                            cwd=novel_backend,
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
                        )
                        for line in poll_result.stdout.strip().split('\n'):
                            if line.startswith('PROGRESS='):
                                prog = int(line.split('=', 1)[1])
                                if prog > prev_progress:
                                    prev_progress = prog
                                    download_tasks[task_id]['transcodeProgress'] = prog
                                    if prog >= 10:
                                        download_tasks[task_id]['detail'] = f'正在生成缩略图...'
                                    if prog >= 20:
                                        download_tasks[task_id]['detail'] = f'正在优化视频...'
                                    if prog >= 30:
                                        download_tasks[task_id]['detail'] = f'正在生成 HLS 流...'
                    except Exception as poll_err:
                        print(f"[Novel] 进度轮询异常: {poll_err}")
                    time.sleep(2)

                encode_stdout, encode_stderr = encode_proc.communicate(timeout=60)

                if encode_stderr:
                    print(f"[Novel] encode stderr: {encode_stderr}")

                if encode_proc.returncode != 0:
                    print(f"[Novel] 转码警告 (exit {encode_proc.returncode}): {encode_stderr}")

                # 步骤3: 设置 Gallery 封面（从视频缩略图创建 GalleryImage）
                download_tasks[task_id]['detail'] = '正在设置封面缩略图...'
                cover_script = (
                    "import os, sys\n"
                    "os.environ['DJANGO_SETTINGS_MODULE'] = 'novel_project.settings'\n"
                    "sys.path.insert(0, " + repr(novel_backend) + ")\n"
                    "import django\n"
                    "django.setup()\n"
                    "from api.models import Gallery, GalleryVideo, GalleryImage\n"
                    "from django.core.files import File\n"
                    f"video = GalleryVideo.objects.get(id={video_id})\n"
                    "gallery = video.gallery\n"
                    "if not gallery.cover_image and video.thumbnail:\n"
                    "    thumb_path = video.thumbnail.path\n"
                    "    with open(thumb_path, 'rb') as f:\n"
                    "        image = GalleryImage.objects.create(\n"
                    "            gallery=gallery, image=File(f, name=os.path.basename(thumb_path)), caption='视频缩略图', order=0\n"
                    "        )\n"
                    "    gallery.cover_image = image\n"
                    "    gallery.save(update_fields=['cover_image'])\n"
                    "    print(f'Cover set: GalleryImage ID={image.id}')\n"
                    "else:\n"
                    "    print('Cover already set or no thumbnail')\n"
                )

                cover_result = _sp.run(
                    [novel_venv_python, '-c', cover_script],
                    capture_output=True, text=True, timeout=30,
                    cwd=novel_backend,
                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
                )
                print(f"[Novel] cover stdout: {cover_result.stdout}")
                if cover_result.stderr:
                    print(f"[Novel] cover stderr: {cover_result.stderr}")

                # 切换到清理阶段
                download_tasks[task_id]['phase'] = 'cleaning'
                download_tasks[task_id]['phaseTitle'] = _phase_title('cleaning')
                download_tasks[task_id]['detail'] = '正在删除临时文件'

                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                        print(f"[Novel] 已清理临时文件: {output_path}")
                    except Exception:
                        pass

                download_tasks[task_id]['status'] = 'completed'
                download_tasks[task_id]['transcodeProgress'] = 100
                download_tasks[task_id]['phase'] = None
                download_tasks[task_id]['phaseTitle'] = ''
                download_tasks[task_id]['novel_video_id'] = video_id
                print(f"[Novel] 入库完成! video_id={video_id}")

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
                    'outputPath': f'Novel DB video_id={video_id}',
                    'fileSize': '',
                    'downloadedAt': int(datetime.now().timestamp() * 1000),
                    'downloadMode': 'novel',
                    'novelVideoId': video_id,
                })
                save_history(history)

            except Exception as e:
                download_tasks[task_id]['status'] = 'error'
                download_tasks[task_id]['error'] = str(e)
                print(f"[Novel] 入库失败: {e}")

        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()

        return jsonify({
            'task_id': task_id,
            'filename': filename,
            'status': 'downloading',
            'downloadMode': 'novel'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500




if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=15678)
    args = parser.parse_args()

    print(f"Starting server on port {args.port}")
    app.run(host='127.0.0.1', port=args.port, debug=False)
