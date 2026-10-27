"""Pure parsers for data delivered to Instagram's browser UI.

These helpers never send requests. Counts used by Benford must be exact;
abbreviated labels such as 1.2K are deliberately left unavailable.
"""
import re
from urllib.parse import urlparse

from . import parsers as P


def objects(value):
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            yield item
            stack.extend(reversed(list(item.values())))
        elif isinstance(item, list):
            stack.extend(reversed(item))


def exact_count(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    text = str(value).strip().replace('\u00a0', ' ')
    # Browser locale is en-US. Do not silently round decimals or K/M labels.
    if re.fullmatch(r'\d+|\d{1,3}(?:,\d{3})+', text):
        return int(text.replace(',', ''))
    return None


def profile_from_payload(payload, username):
    merged = {}
    for raw in objects(payload):
        if str(raw.get('username') or '').casefold() != username.casefold():
            continue
        if not any(key in raw for key in ('biography', 'follower_count', 'edge_followed_by', 'following_count')):
            continue
        normalized = dict(raw)
        for field, connection in (
            ('follower_count', 'edge_followed_by'),
            ('following_count', 'edge_follow'),
            ('all_media_count', 'edge_owner_to_timeline_media'),
        ):
            if field not in normalized and isinstance(raw.get(connection), dict):
                normalized[field] = raw[connection].get('count')
        if 'media_count' in raw and 'all_media_count' not in normalized:
            normalized['all_media_count'] = raw['media_count']
        parsed = P.profile(normalized, normalized) or {}
        for field in ('follower_count', 'following_count'):
            parsed[field] = exact_count(normalized.get(field))
        parsed['post_count'] = exact_count(normalized.get('all_media_count'))
        merged.update({key: value for key, value in parsed.items() if value is not None})
    return merged


def media_from_payload(payload, username, allowed_codes=()):
    result = {}
    for raw in objects(payload):
        code = raw.get('code') or raw.get('shortcode')
        if not code or not any(key in raw for key in ('media_type', '__typename', 'image_versions2', 'display_url', 'video_versions')):
            continue
        owner = raw.get('user') or raw.get('owner') or {}
        author = str(owner.get('username') or '').casefold()
        # Never mix recommended posts or other users' comments into Big Five.
        if author and author != username.casefold():
            continue
        if not author and code not in allowed_codes:
            continue
        normalized = dict(raw)
        normalized['code'] = code
        normalized['pk'] = raw.get('pk') or raw.get('id')
        normalized['user'] = owner or {'username': username}
        if isinstance(normalized.get('caption'), str):
            normalized['caption'] = {'text': normalized['caption']}
        if 'caption' not in normalized:
            edges = (raw.get('edge_media_to_caption') or {}).get('edges') or []
            normalized['caption'] = {'text': (edges[0].get('node') or {}).get('text')} if edges else {}
        normalized.setdefault('taken_at', raw.get('taken_at_timestamp'))
        if 'image_versions2' not in normalized and raw.get('display_url'):
            normalized['image_versions2'] = {'candidates': [{'url': raw['display_url']}]}
        if 'video_versions' not in normalized and raw.get('video_url'):
            normalized['video_versions'] = [{'url': raw['video_url'] }]
        normalized.setdefault('media_type', 2 if raw.get('is_video') else 1)
        for field, connection in (('like_count', 'edge_media_preview_like'), ('comment_count', 'edge_media_to_comment')):
            if field not in normalized and isinstance(raw.get(connection), dict):
                normalized[field] = raw[connection].get('count')
        if raw.get('edge_sidecar_to_children'):
            normalized['media_type'] = 8
            normalized['carousel_media'] = []
            for edge in raw['edge_sidecar_to_children'].get('edges', []):
                child = edge.get('node') or {}
                normalized['carousel_media'].append({
                    'pk': child.get('id'), 'media_type': 2 if child.get('is_video') else 1,
                    'image_versions2': {'candidates': [{'url': child.get('display_url')}]},
                    'video_versions': [{'url': child['video_url']}] if child.get('video_url') else [],
                })
        parsed = P.media(normalized)
        if parsed:
            result[code] = parsed
    return result


def relationship_from_payload(payload, relationship, response_url, target_id):
    """Only extract the selected relationship, never arbitrary 'users' arrays."""
    rows = []
    terminal = None
    limited = False
    path = urlparse(response_url).path
    direct = bool(target_id and f'/friendships/{target_id}/{relationship}/' in path)
    connection_key = 'edge_followed_by' if relationship == 'followers' else 'edge_follow'
    for obj in objects(payload):
        connection = obj.get(connection_key)
        connections = [connection] if isinstance(connection, dict) else []
        connections.extend(value for key, value in obj.items()
                           if f'friendships__{relationship}' in key and isinstance(value, dict))
        if direct and isinstance(obj.get('users'), list):
            rows.extend(obj['users'])
            more = obj.get('has_more', obj.get('big_list'))
            cursor = obj.get('next_max_id')
            if more is not None or cursor is not None:
                terminal = not bool(more or cursor)
            limited = limited or bool(obj.get(f'should_limit_list_of_{relationship}'))
        for connection in connections:
            rows.extend(edge.get('node') or {} for edge in connection.get('edges', []) if isinstance(edge, dict))
            info = connection.get('page_info') or {}
            if 'has_next_page' in info:
                terminal = not bool(info['has_next_page'])
    parsed = {}
    for raw in rows:
        row = P.user_ref(raw)
        if row and row.get('username'):
            row.update({field: exact_count(raw.get(field)) for field in ('follower_count', 'following_count')})
            parsed[row['username'].casefold()] = row
    return parsed, terminal, limited


def media_terminal(payload, kind):
    """Read completion only from timeline/reel connections, not comments."""
    terminal = None
    markers = ('timeline', 'user_timeline', 'profile_posts') if kind == 'posts' else ('clips', 'reels')
    for obj in objects(payload):
        for key, connection in obj.items():
            if not isinstance(connection, dict) or not any(marker in key for marker in markers):
                continue
            info = connection.get('page_info') or {}
            if 'has_next_page' in info:
                terminal = not bool(info['has_next_page'])
    return terminal


def collection_result(rows, key, *, complete=False, limited=False, error=None, stopped=False):
    count_key = {'posts': 'post_count', 'reels': 'reel_count', 'users': 'user_count'}[key]
    status = 'limit_reached' if limited else 'complete' if complete else 'partial' if rows else 'failed'
    return {
        key: rows, count_key: len(rows), 'complete': complete, 'limited': limited,
        'status': status, 'error': error, 'stop_requests': stopped,
        'has_more': not complete, 'next_cursor': None,
    }
