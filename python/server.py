"""
Flask HTTP server - provides API for Electron app.
Supports missav.ws and kissjav.com
"""
import asyncio
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, request, jsonify
from flask_cors import CORS

from crawler import crawler as missav_crawler, downloader as missav_downloader

from image_crawler import ImageGalleryCrawler
from novel_import import import_video_to_novel, import_images_to_novel

# Optional kissjav support
try:
    from kissjav_crawler import kissjav_crawler, kissjav_downloader
    _kissjav_available = True
except ImportError as e:
    print(f"[Server] kissjav_crawler not found: {e}")
    kissjav_crawler = kissjav_downloader = None
    _kissjav_available = False

# Force UTF-8 stdout
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

app = Flask(__name__)
CORS(app)

download_tasks: dict[str, dict] = {}


def _is_xx_knit_bid_gallery_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or '').lower()
    return 'xx.knit.bid' in hostname

# ----- History -----
def get_history_file():
    d = os.environ.get('MISSAV_HISTORY_DIR')
    p = Path(d) if d else Path.home() / '.missav'
    p.mkdir(parents=True, exist_ok=True)
    return p / 'history.json'

HISTORY_FILE = None

def load_history():
    global HISTORY_FILE
    if HISTORY_FILE is None:
        HISTORY_FILE = get_history_file()
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return []

def save_history(records):
    HISTORY_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')

# ----- Utils -----
def get_crawler_for_url(url: str):
    hostname = (urlparse(url).hostname or '')
    if 'kissjav' in hostname:
        if _kissjav_available:
            return kissjav_crawler, kissjav_downloader, 'kissjav'
        raise RuntimeError('kissjav crawler not loaded')
    return missav_crawler, missav_downloader, 'missav'

def run_async(coro):
    loop = asyncio.new_event_loop()
    result, exception = None, None
    def _run():
        nonlocal result, exception
        try:
            result = loop.run_until_complete(coro)
        except Exception as e:
            exception = e
        finally:
            loop.close()
    t = threading.Thread(target=_run)
    t.start()
    t.join()
    if exception:
        raise exception
    return result

def _phase_title(phase):
    return {
        'parsing': '解析图集',
        'download_segments': '下载分片',
        'downloading': '下载中',
        'merging': '合并视频',
        'importing': '入库到 Novel',
        'transcoding': '转码中',
        'cleaning': '清理临时文件',
    }.get(phase, phase or '')


def _poll_transcode(task_id, novel_project_path, video_id):
    """Poll Django GalleryVideo transcode progress."""
    import subprocess
    novel_backend = os.path.join(novel_project_path, 'backend')
    venv_python = os.path.join(novel_backend, 'venv', 'Scripts', 'python.exe')
    if not os.path.exists(venv_python):
        venv_python = 'python'

    download_tasks[task_id]['phase'] = 'transcoding'
    download_tasks[task_id]['phaseTitle'] = _phase_title('transcoding')
    download_tasks[task_id]['detail'] = 'Waiting for transcode...'

    be = novel_backend.replace('\\', '\\\\')
    poll_script = (
        "import os,sys;"
        f"sys.path.insert(0,r'{be}');"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE','novel_project.settings');"
        "import django;django.setup();"
        "from api.models import GalleryVideo;"
        f"v=GalleryVideo.objects.filter(id={video_id}).first();"
        "print(f'STATUS:{v.status}:PROGRESS:{v.progress}') if v else print('NOT_FOUND')"
    )

    start_time = time.time()
    while time.time() - start_time < 1800:  # max 30 min
        try:
            proc = subprocess.run(
                [venv_python, '-c', poll_script],
                capture_output=True, text=True, timeout=10,
                cwd=novel_backend,
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
            )
            stdout = proc.stdout.strip()
            m = re.search(r'STATUS:(\w+):PROGRESS:(\d+)', stdout)
            if m:
                vid_status = m.group(1)
                vid_progress = int(m.group(2))
                download_tasks[task_id]['transcodeProgress'] = vid_progress
                download_tasks[task_id]['detail'] = f'Transcoding: {vid_progress}%'
                if vid_status in ('completed', 'ready', 'failed'):
                    if vid_status == 'failed':
                        download_tasks[task_id]['detail'] = 'Transcode failed'
                    else:
                        download_tasks[task_id]['transcodeProgress'] = 100
                        download_tasks[task_id]['detail'] = 'Transcode completed'
                    break
            elif 'NOT_FOUND' in stdout:
                download_tasks[task_id]['detail'] = f'Video {video_id} not found'
                break
        except Exception as e:
            print(f'[Poll transcode] Error: {e}')
        time.sleep(3)

# ==================== API Routes ====================

@app.route('/api/parse', methods=['POST'])
def parse_video():
    data = request.get_json()
    url = data.get('url', '')
    if not url:
        return jsonify({'error': 'URL required'}), 400
    try:
        crawler, _, source = get_crawler_for_url(url)
        print(f"[Parse] {source}: {url}")
        result = run_async(crawler.parse_video(url))
        result['source'] = source
        return jsonify(result)
    except Exception as e:
        print(f"[Parse] Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def start_download():
    data = request.get_json()
    url = data.get('url', '')
    output_dir = data.get('outputDir', '') or os.path.expanduser('~\\Downloads')
    max_concurrent = data.get('maxConcurrent', 10)
    proxy = data.get('proxy', '')
    auto_merge = data.get('autoMerge', True)
    keep_temp = data.get('keepTempFiles', False)

    if not url:
        return jsonify({'error': 'URL required'}), 400

    crawler, downloader, source = get_crawler_for_url(url)
    downloader.set_proxy(proxy if proxy else None)
    if hasattr(downloader, 'set_concurrent'):
        downloader.set_concurrent(max_concurrent)

    try:
        video_info = run_async(crawler.parse_video(url))
        if source == 'kissjav' and not video_info.get('video_url'):
            return jsonify({'error': 'No video URL found'}), 400
        if source != 'kissjav' and not video_info.get('m3u8_url'):
            return jsonify({'error': 'No m3u8 URL found'}), 400

        task_id = str(uuid.uuid4())[:8]
        safe_title = "".join(c for c in video_info['title'] if c.isalnum() or c in ' _-').strip()[:50]
        filename = f"{video_info.get('code', '') or safe_title}.mp4"
        output_path = os.path.abspath(os.path.join(output_dir, filename))

        download_tasks[task_id] = {
            'id': task_id, 'url': url, 'video_info': video_info,
            'filename': filename, 'output_path': output_path,
            'status': 'downloading', 'progress': 0, 'speed': '0 MB/s',
            'phase': 'downloading', 'phaseTitle': _phase_title('downloading'),
            'detail': '', 'transcodeProgress': 0, 'source': source,
        }

        def _progress(progress, speed, phase=None, detail=None):
            download_tasks[task_id]['progress'] = progress
            download_tasks[task_id]['speed'] = speed
            if phase:
                download_tasks[task_id]['phase'] = phase
                download_tasks[task_id]['phaseTitle'] = _phase_title(phase)
            if detail:
                download_tasks[task_id]['detail'] = detail

        def _download():
            try:
                if source == 'kissjav':
                    run_async(downloader.download_video(video_info['video_url'], 'https://kissjav.com/', output_path, _progress))
                else:
                    run_async(downloader.download_video(video_info['m3u8_url'], url, output_path,
                        auto_merge=auto_merge, keep_temp_files=keep_temp, progress_callback=_progress))
                download_tasks[task_id]['status'] = 'completed'
                download_tasks[task_id]['progress'] = 100
                # Keep phase info visible after completion
                _save_to_history(task_id, video_info, filename, output_path, 'local', source)
            except Exception as e:
                download_tasks[task_id]['status'] = 'error'
                download_tasks[task_id]['error'] = str(e)

        threading.Thread(target=_download, daemon=True).start()
        return jsonify({'task_id': task_id, 'filename': filename, 'status': 'downloading', 'source': source})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-to-novel', methods=['POST'])
def start_download_to_novel():
    data = request.get_json()
    url = data.get('url', '')
    output_dir = data.get('outputDir', '') or os.path.expanduser('~\\Downloads')
    max_concurrent = data.get('maxConcurrent', 10)
    proxy = data.get('proxy', '')
    auto_merge = data.get('autoMerge', True)
    keep_temp = data.get('keepTempFiles', False)
    novel_project_path = data.get('novelProjectPath', '')

    if not url:
        return jsonify({'error': 'URL required'}), 400
    if not novel_project_path:
        return jsonify({'error': 'Novel project path required'}), 400

    crawler, downloader, source = get_crawler_for_url(url)
    downloader.set_proxy(proxy if proxy else None)
    if hasattr(downloader, 'set_concurrent'):
        downloader.set_concurrent(max_concurrent)

    try:
        video_info = run_async(crawler.parse_video(url))
        if source == 'kissjav' and not video_info.get('video_url'):
            return jsonify({'error': 'No video URL found'}), 400
        if source != 'kissjav' and not video_info.get('m3u8_url'):
            return jsonify({'error': 'No m3u8 URL found'}), 400

        task_id = str(uuid.uuid4())[:8]
        safe_title = "".join(c for c in video_info['title'] if c.isalnum() or c in ' _-').strip()[:50]
        filename = f"{video_info.get('code', '') or safe_title}.mp4"
        output_path = os.path.abspath(os.path.join(output_dir, filename))

        download_tasks[task_id] = {
            'id': task_id, 'url': url, 'video_info': video_info,
            'filename': filename, 'output_path': output_path,
            'status': 'downloading', 'progress': 0, 'speed': '0 MB/s',
            'phase': 'downloading', 'phaseTitle': _phase_title('downloading'),
            'detail': '', 'transcodeProgress': 0,
            'downloadMode': 'novel', 'source': source,
        }

        def _progress(progress, speed, phase=None, detail=None):
            download_tasks[task_id]['progress'] = progress
            download_tasks[task_id]['speed'] = speed
            if phase:
                download_tasks[task_id]['phase'] = phase
                download_tasks[task_id]['phaseTitle'] = _phase_title(phase)
            if detail:
                download_tasks[task_id]['detail'] = detail

        def _dl():
            try:
                if source == 'kissjav':
                    run_async(downloader.download_video(video_info['video_url'], 'https://kissjav.com/', output_path, _progress))
                else:
                    run_async(downloader.download_video(video_info['m3u8_url'], url, output_path,
                        auto_merge=auto_merge, keep_temp_files=keep_temp, progress_callback=_progress))

                download_tasks[task_id]['progress'] = 100

                # Import to Novel
                print(f'[Novel] Importing: {filename}')
                download_tasks[task_id]['phase'] = 'importing'
                download_tasks[task_id]['phaseTitle'] = _phase_title('importing')
                download_tasks[task_id]['detail'] = 'Importing...'
                try:
                    cover = video_info.get('cover', '')
                    result = import_video_to_novel(novel_project_path, output_path, safe_title, cover_url=cover, source=source)
                    if result['success']:
                        download_tasks[task_id]['novel_video_id'] = result.get('video_id')
                        # Poll transcode progress
                        vid = result.get('video_id')
                        if vid:
                            _poll_transcode(task_id, novel_project_path, vid)
                        download_tasks[task_id]['detail'] = result['message']
                    else:
                        download_tasks[task_id]['detail'] = result['message'] + (' stdout=' + result.get('stdout','')[:80] if result.get('stdout') else '')
                except Exception as _e:
                    download_tasks[task_id]['detail'] = f'Import error: {str(_e)[:200]}'

                download_tasks[task_id]['phase'] = 'completed'
                download_tasks[task_id]['phaseTitle'] = ''
                download_tasks[task_id]['detail'] = ''
                download_tasks[task_id]['status'] = 'completed'
                _save_to_history(task_id, video_info, filename, output_path, 'novel', source)
            except Exception as e:
                download_tasks[task_id]['status'] = 'error'
                download_tasks[task_id]['error'] = str(e)

        threading.Thread(target=_dl, daemon=True).start()
        return jsonify({'task_id': task_id, 'filename': filename, 'status': 'downloading', 'downloadMode': 'novel', 'source': source})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/gallery/parse', methods=['POST'])
def parse_gallery():
    data = request.get_json()
    gallery_url = data.get('galleryUrl', '')
    proxy = data.get('proxy', '')
    if not gallery_url:
        return jsonify({'error': 'Gallery URL required'}), 400
    try:
        crawler = ImageGalleryCrawler(proxy=proxy)
        result = run_async(crawler.parse_gallery(gallery_url))
        return jsonify({
            'title': result.title,
            'page_url': result.page_url,
            'image_count': len(result.image_urls),
            'image_urls': result.image_urls,
            'has_video': bool(result.video_url),
            'video_count': 1 if result.video_url else 0,
            'video_url': result.video_url,
        })
    except Exception as e:
        print(f"[Gallery Parse] Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gallery/download', methods=['POST'])

def start_gallery_download():
    data = request.get_json()
    gallery_url = data.get('galleryUrl', '')
    download_mode = data.get('downloadMode', 'local')
    novel_project_path = data.get('novelProjectPath', '')
    proxy = data.get('proxy', '')

    if not gallery_url:
        return jsonify({'error': 'Gallery URL required'}), 400

    if download_mode == 'novel':
        if not novel_project_path:
            return jsonify({'error': 'Novel project path required'}), 400
        cache_dir = Path(novel_project_path) / 'img' / 'gallery-cache'
        cache_dir.mkdir(parents=True, exist_ok=True)
        output_dir = str(cache_dir)
    else:
        output_dir = data.get('outputDir', '') or os.path.expanduser('~\\Downloads')

    task_id = str(uuid.uuid4())[:8]
    download_tasks[task_id] = {
        'id': task_id, 'url': gallery_url, 'video_info': {'title': '图集下载'}, 
        'filename': '解析中...', 'output_path': output_dir,
        'status': 'downloading', 'progress': 0, 'speed': '0 张/秒',
        'phase': 'parsing', 'phaseTitle': _phase_title('parsing'),
        'detail': '', 'transcodeProgress': 0,
        'downloadMode': download_mode, 'source': 'gallery',
        'has_video': False, 'video_count': 0, 'media_type': 'gallery',
    }

    def _progress(progress, speed, phase=None, detail=None, extra=None):
        task = download_tasks[task_id]
        task['progress'] = progress
        task['speed'] = speed
        if phase:
            task['phase'] = phase
            task['phaseTitle'] = _phase_title(phase)
        if detail:
            task['detail'] = detail
        if extra:
            task['total_images'] = extra.get('total_images')
            task['current_index'] = extra.get('current_index')
            task['success_count'] = extra.get('success_count')
            task['failed_count'] = extra.get('failed_count')
            if extra.get('title'):
                task['filename'] = extra['title']

    def _download():
        try:
            crawler = ImageGalleryCrawler(proxy=proxy)
            result = run_async(crawler.download_gallery(gallery_url, output_dir, _progress))
            task = download_tasks[task_id]
            task['filename'] = result['filename']
            task['output_path'] = result['output_path']
            task['video_info'] = {'title': result['title'], 'cover': '', 'actresses': [], 'tags': [], 'code': '', 'source_url': gallery_url}
            task['has_video'] = bool(result.get('video_url'))
            task['video_count'] = 1 if result.get('video_url') else 0
            task['media_type'] = 'gallery_with_video' if result.get('video_url') else 'gallery'
            task['detail'] = f"已下载 {result['image_count']} 张图片"
            cache_src_path = result.get('output_path', '')

            if download_mode == 'novel':
                task['phase'] = 'importing'
                task['phaseTitle'] = _phase_title('importing')
                task['detail'] = '正在导入 Novel 图集库...'
                import_result = import_images_to_novel(novel_project_path, result['title'], result['image_paths'])
                if not import_result.get('success'):
                    raise RuntimeError(import_result.get('message') or 'Novel 图片入库失败')
                gallery_id = import_result.get('gallery_id')
                task['gallery_id'] = gallery_id
                task['detail'] = import_result.get('message', '图片入库完成')
                novel_img_dir = os.path.join(novel_project_path, 'img', 'gallery_images', str(gallery_id))
                task['output_path'] = novel_img_dir
                result['output_path'] = novel_img_dir
                video_url = result.get('video_url') or ''
                if gallery_id and video_url and _is_xx_knit_bid_gallery_url(gallery_url):
                    task['phase'] = 'downloading'
                    task['phaseTitle'] = _phase_title('downloading')
                    task['detail'] = '图片已入库，正在下载附带视频...'
                    cache_video_dir = Path(novel_project_path) / 'img' / 'gallery-cache-video'
                    cache_video_dir.mkdir(parents=True, exist_ok=True)
                    safe_name = "".join(c for c in result['title'] if c.isalnum() or c in ' _-').strip()[:50] or 'gallery_video'
                    video_output_path = str((cache_video_dir / f"{safe_name}.mp4").resolve())
                    missav_downloader.set_proxy(proxy if proxy else None)
                    run_async(
                        missav_downloader.download_video(
                            video_url,
                            gallery_url,
                            video_output_path,
                            auto_merge=True,
                            keep_temp_files=False,
                        )
                    )
                    task['phase'] = 'importing'
                    task['phaseTitle'] = _phase_title('importing')
                    task['detail'] = '正在把附带视频挂到同一个 Gallery...'
                    video_import_result = import_video_to_novel(
                        novel_project_path,
                        video_output_path,
                        result['title'],
                        cover_url='',
                        source='missav',
                        gallery_id=gallery_id,
                    )
                    if not video_import_result.get('success'):
                        raise RuntimeError(video_import_result.get('message') or 'Novel 视频入库失败')
                    task['novel_video_id'] = video_import_result.get('video_id')
                    task['detail'] = (
                        f"{import_result.get('message', '图片入库完成')}；"
                        f"{video_import_result.get('message', '视频入库完成')}"
                    )
                    try:
                        if os.path.exists(video_output_path):
                            os.remove(video_output_path)
                    except Exception as cleanup_err:
                        print(f"[Gallery] 视频缓存清理跳过: {cleanup_err}")
                import shutil
                try:
                    gallery_dir = Path(cache_src_path)
                    if gallery_dir.exists() and gallery_dir.parent.name in ('gallery-cache', 'gallery_images'):
                        shutil.rmtree(gallery_dir, ignore_errors=True)
                        print(f"[Gallery] 清理缓存目录: {gallery_dir}")
                except Exception as cleanup_err:
                    print(f"[Gallery] 缓存清理跳过: {cleanup_err}")

            task['status'] = 'completed'
            task['progress'] = 100
            _save_gallery_to_history(task_id, result, download_mode)
        except Exception as e:
            download_tasks[task_id]['status'] = 'error'
            download_tasks[task_id]['error'] = str(e)

    threading.Thread(target=_download, daemon=True).start()
    return jsonify({'task_id': task_id, 'filename': '解析中...', 'status': 'downloading', 'downloadMode': download_mode, 'source': 'gallery'})

# ----- Common helpers -----

def _save_to_history(task_id, video_info, filename, output_path, mode, source):
    record = {
        'id': task_id, 'title': video_info['title'], 'filename': filename,
        'cover': video_info.get('cover', ''),
        'actresses': video_info.get('actresses', []),
        'tags': video_info.get('tags', []),
        'code': video_info.get('code', ''),
        'outputPath': output_path,
        'downloadedAt': int(time.time() * 1000),
        'downloadMode': mode, 'source': source,
    }
    try:
        history = load_history()
        history.insert(0, record)
        save_history(history[:200])
    except Exception as e:
        print(f"History save failed: {e}")

def _save_gallery_to_history(task_id, result, mode):
    record = {
        'id': task_id, 'title': result.get('title', ''), 'filename': result.get('filename', ''),
        'cover': '', 'actresses': [], 'tags': ['gallery'], 'code': '',
        'outputPath': result.get('output_path', ''),
        'fileSize': f"{result.get('image_count', 0)} 张图片",
        'downloadedAt': int(time.time() * 1000),
        'downloadMode': mode, 'source': 'gallery',
    }
    try:
        history = load_history()
        history.insert(0, record)
        save_history(history[:200])
    except Exception as e:
        print(f"Gallery history save failed: {e}")

@app.route('/api/download-status/<task_id>', methods=['GET'])
def get_download_status(task_id):
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

@app.route('/api/pause-download/<task_id>', methods=['POST'])
def pause_download(task_id):
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    source = task.get('source', 'missav')
    d = kissjav_downloader if (source == 'kissjav' and _kissjav_available) else missav_downloader
    d.pause_task(task_id)
    task['status'] = 'paused'
    return jsonify({'status': 'paused'})

@app.route('/api/resume-download/<task_id>', methods=['POST'])
def resume_download(task_id):
    task = download_tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    source = task.get('source', 'missav')
    d = kissjav_downloader if (source == 'kissjav' and _kissjav_available) else missav_downloader
    d.resume_task(task_id)
    task['status'] = 'downloading'
    return jsonify({'status': 'downloading'})

@app.route('/api/history', methods=['GET'])
def get_history():
    return jsonify(load_history())

@app.route('/api/history/<record_id>', methods=['DELETE'])
def delete_history(record_id):
    history = load_history()
    save_history([r for r in history if r.get('id') != record_id])
    return jsonify({'success': True})

@app.route('/api/history', methods=['DELETE'])
def clear_history():
    save_history([])
    return jsonify({'success': True})

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': int(time.time() * 1000)})

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=15678)
    args = parser.parse_args()
    print(f"Starting server on port {args.port}")
    app.run(host='127.0.0.1', port=args.port, debug=False)


