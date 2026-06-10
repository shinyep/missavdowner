# -*- coding: utf-8 -*-
"""
Novel project video/image import helpers.
"""
import os
import sys


def import_video_to_novel(novel_project_path: str, output_path: str, title: str, cover_url: str = '', source: str = 'missav') -> dict:
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

    # 根据来源选择正确的 Referer
    referer_map = {
        'missav': 'https://missav.ws/',
        'kissjav': 'https://kissjav.com/',
    }
    referer_url = referer_map.get(source, 'https://missav.ws/')

    if cover_url:
        lines += [
            f"cover_url = r'{cu}'",
            f"referer_url = r'{referer_url}'",
            "if not gallery.cover_image and cover_url:",
            "    try:",
            "        import urllib.request, ssl",
            "        ctx = ssl._create_unverified_context()",
            "        req = urllib.request.Request(cover_url, headers={",
            "            'Referer': referer_url,",
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


def import_images_to_novel(novel_project_path: str, title: str, image_paths: list[str]) -> dict:
    novel_backend = os.path.join(novel_project_path, 'backend')
    venv_python = os.path.join(novel_backend, 'venv', 'Scripts', 'python.exe')
    if not os.path.exists(venv_python):
        venv_python = 'python'

    safe_title = (title or 'Untitled Gallery')[:200]
    existing_paths = [os.path.abspath(path) for path in image_paths if os.path.exists(path)]
    if not existing_paths:
        return {'success': False, 'gallery_id': None, 'message': 'No image files to import'}

    django_script = '\n'.join([
        'import os, sys',
        f"sys.path.insert(0, {repr(novel_backend)})",
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'novel_project.settings')",
        'import django; django.setup()',
        'from pathlib import Path',
        'from django.core.files import File',
        'from api.models import Gallery, GalleryImage',
        f'title = {repr(safe_title)}',
        f'image_paths = {repr(existing_paths)}',
        'gallery, created = Gallery.objects.get_or_create(title=title)',
        "existing_captions = set(GalleryImage.objects.filter(gallery=gallery).values_list('caption', flat=True))",
        "order = GalleryImage.objects.filter(gallery=gallery).count()",
        'created_ids = []',
        'for image_path in image_paths:',
        '    path = Path(image_path)',
        '    if not path.exists():',
        '        continue',
        "    order += 1",
        "    caption = f'{gallery.id}_{order:03d}{path.suffix.lower() or '.jpg'}'",
        '    if caption in existing_captions:',
        '        continue',
        "    with path.open('rb') as file_obj:",
        '        image = GalleryImage(gallery=gallery, caption=caption, order=order)',
        '        image.image.save(caption, File(file_obj), save=True)',
        '    created_ids.append(image.id)',
        '    existing_captions.add(caption)',
        '    if not gallery.cover_image:',
        '        gallery.cover_image = image',
        '        gallery.save(update_fields=["cover_image"])',
        "print(f'GALLERY_ID:{gallery.id}')",
        "print(f'IMAGES_CREATED:{len(created_ids)}')",
    ])

    import re
    import subprocess
    try:
        proc = subprocess.run(
            [venv_python, '-c', django_script],
            capture_output=True, text=True, timeout=300,
            cwd=novel_backend,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip() if proc.stderr else ''
        gallery_match = re.search(r'GALLERY_ID:(\d+)', stdout)
        count_match = re.search(r'IMAGES_CREATED:(\d+)', stdout)
        if proc.returncode == 0 and gallery_match:
            gallery_id = int(gallery_match.group(1))
            image_count = int(count_match.group(1)) if count_match else 0
            return {
                'success': True,
                'gallery_id': gallery_id,
                'image_count': image_count,
                'message': f'Import OK (gallery_id={gallery_id}, images={image_count})',
                'stdout': stdout,
                'stderr': stderr,
            }
        return {
            'success': False,
            'gallery_id': None,
            'message': f'Import failed (rc={proc.returncode})',
            'stdout': stdout,
            'stderr': stderr,
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'gallery_id': None, 'message': 'Import timeout'}
    except Exception as e:
        return {'success': False, 'gallery_id': None, 'message': f'Import exception: {str(e)}'}

