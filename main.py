"""Application workflows: Playwright + session cookies, Gemini analysis and files."""
import argparse
import csv
import json
import re
import time
from pathlib import Path

import benford
from config import gemini_api_key, gemini_model
from gemini_client import analyze_texts, GeminiError
from instagram import refs
from instagram.browser import InstagramBrowser, CollectionCancelled, login_session
from instagram.errors import InstagramBlocked, InstagramGated
from instagram.media_download import download_content

OUTPUT_DIR = Path(__file__).resolve().parent / 'output'
HASHTAG_RE = re.compile(r'(?<![\w])#[\w]+', re.UNICODE)
MENTION_RE = re.compile(r'(?<![\w.])@[\w.]+', re.UNICODE)


def _target(raw_username):
    user = refs.resolve_user(raw_username)
    if not user.get('username'):
        raise ValueError('Escribe el @handle de Instagram, no un ID numérico.')
    return user


def _limit(value):
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
        raise ValueError('El límite debe ser un entero positivo o None para todo lo disponible.')
    return value


def _progress(callback, message):
    print(message)
    if callback:
        callback(message)


def _metadata(result):
    return {key: result.get(key) for key in ('complete', 'status', 'error', 'limited')}


def _not_requested(key, message):
    return {key: [], 'complete': False, 'status': 'not_requested', 'error': message, 'stop_requests': True}


def _content_record(item, source):
    caption = item.get('caption') or ''
    stats = item.get('stats') or {}
    return {
        'id': item.get('id'), 'code': item.get('code'), 'source': source,
        '_media': {'image': item.get('image'), 'video': item.get('video'), 'carousel': item.get('carousel') or []},
        'format': item.get('type') or 'unknown', 'url': item.get('link'),
        'date': item.get('published_at'), 'caption': caption,
        'hashtags': list(dict.fromkeys(HASHTAG_RE.findall(caption))),
        'mentions': list(dict.fromkeys(MENTION_RE.findall(caption))),
        'metrics': {'likes': stats.get('like_count'), 'comments': stats.get('comment_count'),
                    'views': stats.get('view_count') if stats.get('view_count') is not None else stats.get('play_count')},
    }


def save_report(username, report):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f'instagram_report_{username}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def run_export(raw_username, limit=None, *, progress=None, cancel=None, client_factory=None):
    """Collect profile/content and analyze text with the configured Gemini API."""
    if not gemini_api_key():
        raise GeminiError('Falta GEMINI_API_KEY. Agrégala al archivo .env y reinicia la aplicación.')
    user = _target(raw_username)
    limit = _limit(limit)
    factory = client_factory or InstagramBrowser
    with factory(progress=progress, cancel=cancel) as scraper:
        profile = scraper.get_profile(user)
        posts = scraper.collect_media(user, 'posts', limit)
        if posts['stop_requests']:
            reels = _not_requested('reels', 'Consulta detenida tras la interrupción de publicaciones.')
        else:
            reels = scraper.collect_media(user, 'reels', limit)
    records = [_content_record(item, 'publicación') for item in posts['posts']]
    records += [_content_record(item, 'reel') for item in reels['reels']]
    unique = {}
    for row in records:
        key = row.get('code') or row.get('id') or row.get('url')
        if key:
            unique.setdefault(key, row)
    all_content = sorted(unique.values(), key=lambda row: row.get('date') or '', reverse=True)
    content = all_content[:limit]
    stopped = posts['stop_requests'] or reels['stop_requests'] or bool(cancel and cancel.is_set())
    if stopped:
        for item in content:
            item['media_downloads'] = {'status': 'not_requested', 'files': [], 'error': 'Recopilación interrumpida.'}
    else:
        _progress(progress, 'Guardando fotos y videos disponibles...')
        download_content(user['username'], content, OUTPUT_DIR, cancel=cancel)
    for item in content:
        item.pop('_media', None)
    _progress(progress, 'Analizando textos con Gemini API...')
    analysis_error = None
    try:
        analysis = analyze_texts(profile, content)
    except GeminiError as exc:
        analysis = None
        analysis_error = str(exc)
    truncated = limit is not None and len(all_content) > limit
    complete = posts.get('complete') and reels.get('complete') and not truncated
    status = 'complete' if complete else 'partial' if content else 'failed'
    if not stopped and (truncated or posts.get('limited') or reels.get('limited')):
        status = 'limit_reached'
    report = {
        'target': user['username'], 'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'extractor': 'playwright_browser', 'status': status,
        'profile': {
            'username': profile.get('username') or user['username'], 'full_name': profile.get('full_name'),
            'biography': profile.get('biography'), 'is_private': profile.get('is_private'),
            'counts': {'posts': profile.get('post_count'), 'followers': profile.get('follower_count'), 'following': profile.get('following_count')},
            'links': {'bio': profile.get('bio_links') or [], 'external': profile.get('external_link')},
        },
        'content': {'requested_limit': limit, 'count': len(content), 'items': content,
                    'collection': {'posts': _metadata(posts), 'reels': _metadata(reels)}},
        'personality_analysis': {
            'status': 'completed' if analysis is not None else 'failed',
            'provider': 'gemini_api', 'model': (analysis or {}).get('model') or gemini_model(),
            'source_collection_status': status, 'result': analysis, 'error': analysis_error,
        },
    }
    path = save_report(user['username'], report)
    _progress(progress, f'Contenido: {len(content)} elementos; estado {status}. Informe: {path}')
    return report, path


def benford_datasets(data):
    return {
        'followers_of_followers': benford.analyze_dataset(data, 'followers', 'follower_count'),
        'following_of_following': benford.analyze_dataset(data, 'following', 'following_count'),
    }


def run_benford_scan(raw_username, *, limit=None, progress=None, cancel=None, client_factory=None):
    user = _target(raw_username)
    limit = _limit(limit)
    factory = client_factory or InstagramBrowser
    with factory(progress=progress, cancel=cancel) as scraper:
        followers = scraper.collect_relationship(user, 'followers', limit)
        if followers['stop_requests']:
            following = _not_requested('users', 'Consulta detenida tras la interrupción de seguidores.')
        else:
            following = scraper.collect_relationship(user, 'following', limit)
        interrupted = followers['stop_requests'] or following['stop_requests']
        unique = {}
        for row in followers['users'] + following['users']:
            key = (row.get('username') or str(row.get('id') or '')).casefold()
            if key:
                unique.setdefault(key, dict(row))
        for index, row in enumerate(unique.values(), 1):
            if interrupted or (cancel and cancel.is_set()):
                interrupted = True
                row['stats_error'] = 'No consultado: recopilación interrumpida.'
                continue
            _progress(progress, f'Leyendo métricas de @{row.get("username")}: {index}/{len(unique)}...')
            try:
                profile = scraper.get_profile(row)
                for key in ('full_name', 'follower_count', 'following_count', 'is_private', 'is_verified', 'link'):
                    if profile.get(key) is not None:
                        row[key] = profile[key]
                if row.get('follower_count') is None or row.get('following_count') is None:
                    row['stats_error'] = 'No se proporcionaron ambos conteos exactos; los valores abreviados no se estiman.'
            except Exception as exc:
                row['stats_error'] = str(exc)[:500]
                interrupted = isinstance(exc, (InstagramBlocked, InstagramGated, CollectionCancelled))
        def enrich(rows):
            return [unique.get((row.get('username') or str(row.get('id') or '')).casefold(), row) for row in rows]
        result = {
            'target': user['username'], 'extractor': 'playwright_browser',
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'requested_limit_per_list': limit,
            'followers': enrich(followers['users']), 'following': enrich(following['users']),
            'collection': {'followers': _metadata(followers), 'following': _metadata(following), 'metrics_interrupted': interrupted},
        }
    has_rows = bool(result['followers'] or result['following'])
    missing_metrics = any(row.get('stats_error') for row in result['followers'] + result['following'])
    result['status'] = ('complete' if followers.get('complete') and following.get('complete') and not interrupted and not missing_metrics
                        else 'partial' if has_rows else 'failed')
    result['analysis'] = benford_datasets(result)
    result['interpretation_note'] = 'El ajuste a Benford no demuestra que una cuenta sea orgánica, falsa ni fraudulenta.'
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / f'benford_scan_{user["username"]}.csv'
    json_path = OUTPUT_DIR / f'benford_scan_{user["username"]}.json'
    fields = ('relationship', 'username', 'full_name', 'follower_count', 'following_count', 'is_private', 'is_verified', 'link', 'stats_error')
    with csv_path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for kind in ('followers', 'following'):
            for row in result[kind]:
                writer.writerow({'relationship': kind, **row})
    result['files'] = {'csv': str(csv_path.resolve()), 'json': str(json_path.resolve())}
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    _progress(progress, f'Benford: estado {result["status"]}; {len(result["followers"])} seguidores, {len(result["following"])} seguidos. CSV: {csv_path}')
    return result


def reanalyze_saved_report(raw_username):
    user = _target(raw_username)
    path = OUTPUT_DIR / f'instagram_report_{user["username"]}.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    try:
        analysis = analyze_texts(report.get('profile') or {}, (report.get('content') or {}).get('items') or [])
        error = None
    except GeminiError as exc:
        analysis = None
        error = str(exc)
    report['personality_analysis'] = {
        'status': 'completed' if analysis is not None else 'failed', 'provider': 'gemini_api',
        'model': (analysis or {}).get('model') or gemini_model(), 'result': analysis, 'error': error,
    }
    return save_report(user['username'], report)


def main():
    parser = argparse.ArgumentParser(description='Instagram con Playwright y cookies; análisis Big Five con Gemini API.')
    parser.add_argument('username', nargs='?', help='handle del perfil')
    parser.add_argument('--mode', choices=['bigfive', 'benford'], default='bigfive')
    parser.add_argument('--limit', type=int, help='máximo de contenidos o cuentas por lista; omitir para todo lo disponible')
    parser.add_argument('--login', action='store_true', help='guardar una sesión iniciada manualmente en el navegador')
    parser.add_argument('--reanalyze', metavar='HANDLE', help='recalcular Big Five con Gemini usando un informe guardado')
    args = parser.parse_args()
    if args.login:
        login_session(progress=print)
    elif args.reanalyze:
        print(reanalyze_saved_report(args.reanalyze))
    else:
        username = args.username or input('Usuario de Instagram: ').strip()
        if args.mode == 'benford':
            run_benford_scan(username, limit=args.limit, progress=None)
        else:
            run_export(username, args.limit, progress=None)


if __name__ == '__main__':
    main()
