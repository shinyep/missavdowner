"""
Novel project video import script.
"""
import os
import sys


def import_video_to_novel(novel_project_path: str, output_path: str, title: str, cover_url: str = '') -> dict:
    novel_backend = os.path.join(novel_project_path, 'backend')
    venv_python = os.path.join(novel_backend, 'venv', 'Scripts', 'python.exe')
    if not os.path.exists(venv_python):
        venv_python = 'python'

    be = novel_backend.replace('\\', '\\\\')
    ti = title.replace("'", "\\'")
    op = output_path.replace('\\', '\\\\')
    cu = cover_url.replace('\\', '\\\\')

    lines = [
        "import os, sys",
        f"sys.path.insert(0, r'{be}')",
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'novel_project.settings')",
        "import django; django.setup()",
        "from api.models import Gallery, GalleryVideo, GalleryImage",
        "from django.core.files import File",
        "from django.core.files.base import ContentFile",
        "from pathlib import Path",
        "",
        f"title = r'{ti}'",
        f"output_path = r'{op}'",
        "",
        "gallery, created = Gallery.objects.get_or_create(title=title)",
        "print(f'GALLERY_ID:{gallery.id}')",
        "",
    ]

    if cover_url:
        lines += [
            f"cover_url = r'{cu}'",
            "if not gallery.cover_image and cover_url:",
            "    try:",
            "        import urllib.request, ssl",
            "        ctx = ssl._create_unverified_context()",
            "        req = urllib.request.Request(cover_url, headers={",
            "            'Referer': 'https://kissjav.com/',",
            "            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'",
            "        })",
            "        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:",
            "            img_data = resp.read()",
            "            img = GalleryImage(gallery=gallery, order=0)",
            "            img.image.save('cover.jpg', ContentFile(img_data), save=True)",
            "            gallery.cover_image = img",
            "            gallery.save()",
            "            print(f'COVER_SET:{img.id}')",
            "    except Exception as e:",
            "        print(f'COVER_SKIP:{e}')",
            "",
        ]

    lines += [
        "video_path = Path(output_path)",
        "if video_path.exists():",
        "    cnt = GalleryVideo.objects.filter(gallery=gallery).count()",
        "    caption = f'{gallery.id}_{cnt+1:03d}_{video_path.name}'",
        "    with open(output_path, 'rb') as f:",
        "        df = File(f, name=caption)",
        "        video = GalleryVideo.objects.create(",
        "            gallery=gallery, video_file=df, caption=caption,",
        "            order=cnt+1, status='pending', progress=0",
        "        )",
        "    print(f'VIDEO_CREATED:{video.id}')",
        "else:",
        "    print('ERROR: Video file not found')",
    ]

    django_script = '\n'.join(lines)

    import subprocess
    try:
        proc = subprocess.run(
            [venv_python, '-c', django_script],
            capture_output=True, text=True, timeout=120,
            cwd=novel_backend,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip() if proc.stderr else ''

        if proc.returncode == 0 and 'VIDEO_CREATED' in stdout:
            import re
            match = re.search(r'VIDEO_CREATED:(\d+)', stdout)
            if match:
                video_id = int(match.group(1))
                subprocess.Popen(
                    [venv_python, 'manage.py', 'process_videos', '--video_id', str(video_id)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    cwd=novel_backend,
                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
                )
                return {
                    'success': True, 'video_id': video_id,
                    'message': f'Import OK (video_id={video_id}), transcode triggered',
                    'stdout': stdout, 'stderr': stderr,
                }
            return {'success': True, 'video_id': None, 'message': 'Import OK', 'stdout': stdout, 'stderr': stderr}
        else:
            return {'success': False, 'video_id': None, 'message': f'Import failed (rc={proc.returncode})', 'stdout': stdout, 'stderr': stderr}
    except subprocess.TimeoutExpired:
        return {'success': False, 'video_id': None, 'message': 'Import timeout'}
    except Exception as e:
        return {'success': False, 'video_id': None, 'message': f'Import exception: {str(e)}'}
