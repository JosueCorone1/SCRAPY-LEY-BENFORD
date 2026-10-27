"""Real Chromium, fully intercepted synthetic pages. No Instagram traffic."""
import json
import os
from html import escape
from urllib.parse import urlparse

import pytest

import main
from instagram import browser

pytestmark = pytest.mark.skipif(os.environ.get('RUN_BROWSER_TESTS') != '1', reason='Set RUN_BROWSER_TESTS=1 and install Chromium')


def profile(username, followers=1, following=1, posts=2):
    return {'pk': {'demo': '1', 'alice': '2'}.get(username, '3'), 'username': username,
            'full_name': username.title(), 'biography': 'arte creativo aprender rutina ' * 30,
            'follower_count': followers, 'following_count': following, 'media_count': posts}


def media(code, video=False):
    return {'pk': '10' if code == 'A1' else '11', 'code': code, 'media_type': 2 if video else 1,
            'product_type': 'clips' if video else 'feed', 'user': {'username': 'demo', 'pk': '1'},
            'caption': {'text': 'Un texto de prueba que pertenece al perfil.'}, 'taken_at': 1700000000,
            'like_count': 5, 'comment_count': 0}


def html(payload, body):
    return f'<html><body><script type="application/json">{json.dumps(payload)}</script>{body}</body></html>'


@pytest.fixture
def routed_factory(monkeypatch, tmp_path):
    monkeypatch.setattr(browser, 'AUTH_DIR', tmp_path / '.auth')
    monkeypatch.setattr(browser, 'STATE_FILE', tmp_path / '.auth/state.json')
    monkeypatch.setattr(browser, 'COOLDOWN_FILE', tmp_path / '.auth/cooldown.json')
    monkeypatch.setattr(browser.config, 'instagram_cookies', lambda: 'sessionid=synthetic-test-only')
    monkeypatch.setattr(browser.config, 'playwright_headless', lambda: True)
    monkeypatch.setattr(browser.config, 'INSTAGRAM_REQUEST_INTERVAL_SECONDS', .05)
    monkeypatch.setattr(main, 'OUTPUT_DIR', tmp_path / 'output')
    monkeypatch.setattr(main, 'download_content', lambda *args, **kwargs: [])
    dialog = "event.preventDefault();document.body.insertAdjacentHTML('beforeend','<div role=\"dialog\"><a href=\"/alice/\">Alice</a></div>');fetch('/fixture/' + this.href.split('/').filter(Boolean).pop() + '.json');"
    header = f'<header><a href="/demo/followers/" onclick="{escape(dialog, quote=True)}">1 followers</a><a href="/demo/following/" onclick="{escape(dialog, quote=True)}">1 following</a></header>'
    responses = {
        '/demo/': (200, html({'user': profile('demo'), 'items': [media('A1'), media('B2', True)]},
                             header + '<main><a href="/p/A1/">Post</a><a href="/reel/B2/">Reel</a></main>')),
        '/demo/reels/': (200, html({'polaris_clips_connection': {'page_info': {'has_next_page': False}, 'items': [media('B2', True)]}},
                                   '<main><a href="/reel/B2/">Reel</a></main>')),
        '/p/A1/': (200, html({'items': [media('A1')]}, '<main>Post</main>')),
        '/reel/B2/': (200, html({'items': [media('B2', True)]}, '<main>Reel</main>')),
        '/alice/': (200, html({'user': profile('alice', 123, 234, 0)}, '<header>Alice</header>')),
        '/fixture/followers.json': (200, json.dumps({'edge_followed_by': {'edges': [{'node': {'pk': '2', 'username': 'alice'}}], 'page_info': {'has_next_page': False}}})),
        '/fixture/following.json': (200, json.dumps({'edge_follow': {'edges': [{'node': {'pk': '2', 'username': 'alice'}}], 'page_info': {'has_next_page': False}}})),
    }
    requests = []
    class RoutedBrowser(browser.InstagramBrowser):
        def __enter__(self):
            super().__enter__()
            def fulfill(route):
                if self.halt_error:
                    route.abort()
                    return
                path = urlparse(route.request.url).path
                requests.append(path)
                status, body = responses.get(path, (404, 'Not found'))
                route.fulfill(status=status, body=body, content_type='application/json' if path.endswith('.json') else 'text/html', headers={'Retry-After': '60'} if status == 429 else {})
            self.context.route('**/*', fulfill)
            return self
    return RoutedBrowser, responses, requests


def test_real_browser_profile_posts_reels_and_local_big_five(routed_factory):
    factory, _, requests = routed_factory
    report, path = main.run_export('demo', client_factory=factory)
    assert path.is_file() and report['status'] == 'complete'
    assert report['content']['count'] == 2
    assert report['profile']['biography'].startswith('arte creativo')
    assert report['personality_analysis']['result']['apertura_a_la_experiencia']['score'] == 75
    assert '/p/A1/' in requests and '/reel/B2/' in requests


def test_real_browser_relationship_dialogs_and_metrics(routed_factory):
    factory, _, requests = routed_factory
    result = main.run_benford_scan('demo', client_factory=factory)
    assert result['status'] == 'complete'
    assert result['followers'][0]['username'] == 'alice'
    assert result['followers'][0]['follower_count'] == 123
    assert result['following'][0]['following_count'] == 234
    assert requests.count('/alice/') == 1


def test_real_browser_429_stops_and_reports_failed(routed_factory):
    factory, responses, requests = routed_factory
    responses['/demo/'] = (429, 'Please wait a few minutes before you try again.')
    result = main.run_benford_scan('demo', client_factory=factory)
    assert result['status'] == 'failed'
    assert result['followers'] == [] and result['following'] == []
    assert '429' in result['collection']['followers']['error']
    assert requests == ['/demo/']
    assert browser.cooldown_remaining() > 0
