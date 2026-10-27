"""Deterministic tests of local calculations, browser parsing and workflows."""
import csv
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import benford
import big_five
import main
from instagram import browser
from instagram.browser_data import collection_result, exact_count, media_from_payload, profile_from_payload, relationship_from_payload
from instagram.errors import InstagramBlocked, InstagramGated, InstagramRateLimited


@pytest.mark.parametrize('value, expected', [(123, 1), (0.0045, 4), ('2.5e8', 2), ('1,234', 1), (0, None), (-5, None), (None, None), (float('nan'), None)])
def test_first_digit(value, expected):
    assert benford.first_significant_digit(value) == expected


def test_benford_empty_sample():
    result = benford.analyze_counts([0, None, -1, 'invalid'])
    assert result['sample_size'] == 0
    assert result['chi_square'] is None and result['p_value'] is None


def test_benford_known_distribution_and_counterexample():
    counts = [301, 176, 125, 97, 79, 67, 58, 51, 46]
    result = benford.analyze_counts([d for d, n in enumerate(counts, 1) for _ in range(n)])
    assert sum(result['expected'].values()) == pytest.approx(1000)
    assert result['proportions'][1] == pytest.approx(0.3010299956639812)
    assert result['degrees_of_freedom'] == 8
    assert result['chi_square'] < 0.01 and result['p_value'] > .99
    assert benford.analyze_counts(list(range(1, 10)) * 100)['p_value'] < .001


@pytest.mark.parametrize('value, expected', [('1,234', 1234), ('1.2K', None), ('1,2 mil', None), (True, None), (0, 0), (-3, None), ('1234', 1234), ('1,2', None)])
def test_exact_counts(value, expected):
    assert exact_count(value) == expected


def test_profile_is_scoped_to_target_and_preserves_zero():
    data = {'data': [{'username': 'other', 'biography': 'wrong', 'follower_count': 999},
                     {'username': 'demo', 'biography': 'correct', 'pk': '1', 'follower_count': 0, 'following_count': 123}]}
    parsed = profile_from_payload(data, 'demo')
    assert parsed['biography'] == 'correct' and parsed['follower_count'] == 0
    assert parsed['following_count'] == 123


def test_recommended_posts_are_not_big_five_evidence():
    media = {'code': 'AB', 'pk': '10', 'media_type': 1, 'user': {'username': 'other'}, 'caption': {'text': 'wrong'}}
    assert media_from_payload({'items': [media]}, 'demo', {'AB'}) == {}
    media['user']['username'] = 'demo'
    assert media_from_payload({'items': [media]}, 'demo')['AB']['caption'] == 'wrong'


def test_relationships_do_not_capture_unrelated_users():
    data = {'users': [{'username': 'someone', 'pk': '2'}], 'has_more': False}
    assert relationship_from_payload(data, 'followers', 'https://www.instagram.com/explore/', '1')[0] == {}
    rows, terminal, _ = relationship_from_payload(data, 'followers', 'https://www.instagram.com/api/v1/friendships/1/followers/', '1')
    assert list(rows) == ['someone'] and terminal is True


def test_cookie_header_validation():
    result = browser.cookies_from_header('sessionid=test-only; csrftoken=example')
    assert all(item['domain'] == '.instagram.com' and item['secure'] for item in result)
    with pytest.raises(ValueError, match='sessionid'):
        browser.cookies_from_header('csrftoken=example')


@pytest.mark.parametrize('status, expected', [(429, InstagramRateLimited), (401, InstagramGated), (403, InstagramBlocked)])
def test_browser_response_classification_and_cooldown(status, expected, monkeypatch, tmp_path):
    monkeypatch.setattr(browser, 'AUTH_DIR', tmp_path)
    monkeypatch.setattr(browser, 'COOLDOWN_FILE', tmp_path / 'cooldown.json')
    session = browser.InstagramBrowser()
    response = SimpleNamespace(url='https://www.instagram.com/demo/', status=status,
                               request=SimpleNamespace(resource_type='document'), headers={'retry-after': '120'})
    session._on_response(response)
    with pytest.raises(expected):
        session._check()
    if status == 429:
        assert 118 < browser.cooldown_remaining() <= 120
        with pytest.raises(InstagramRateLimited):
            browser.InstagramBrowser().__enter__()
    route = Mock()
    session._route(route)
    route.abort.assert_called_once()
    route.continue_.assert_not_called()


def test_cancellation_aborts_new_requests():
    cancel = threading.Event()
    session = browser.InstagramBrowser(cancel=cancel)
    cancel.set()
    with pytest.raises(browser.CollectionCancelled):
        session._check()
    route = Mock()
    session._route(route)
    route.abort.assert_called_once()


def test_sparse_text_has_no_personality_scores():
    result = big_five.analyze_texts({'biography': 'arte creatividad'}, [])
    assert all(result[key]['score'] is None for key in big_five.LEXICONS)


def test_local_score_is_reproducible_and_includes_evidence():
    text = 'arte creativo aprender rutina ' * 30
    result = big_five.analyze_texts({'biography': text}, [])
    trait = result['apertura_a_la_experiencia']
    assert result['word_count'] == 120
    assert trait['score'] == 75
    assert trait['positive_hits'] == 90 and trait['opposite_hits'] == 30
    assert trait['evidence']['positive']['arte'] == 30
    assert result['amabilidad']['score'] is None
    assert big_five.analyze_texts({'biography': text}, []) == result


def test_handles_and_links_are_not_lexical_evidence():
    assert big_five.tokens('https://example.org/arte @creativo #amigos') == []


@pytest.mark.parametrize('path', ['/p/A1/', '/reel/A1/', '/demo/p/A1/', '/demo/reel/A1/'])
def test_media_links_support_profile_prefix(path):
    assert browser.POST_PATH.fullmatch(path)[1] == 'A1'


class FakeBrowser:
    def __init__(self, **kwargs):
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def get_profile(self, user):
        self.calls.append(('profile', user['username']))
        return {'username': user['username'], 'follower_count': 123, 'following_count': 234, 'biography': 'arte creativo aprender rutina ' * 30}
    def collect_media(self, user, kind, limit=None):
        self.calls.append((kind, limit))
        return collection_result([{'id': '1', 'code': 'A1', 'caption': 'example', 'stats': {'view_count': 0}}], kind, complete=True)
    def collect_relationship(self, user, kind, limit=None):
        self.calls.append((kind, limit))
        return collection_result([{'username': 'shared', 'id': '2'}], 'users', complete=True)


@pytest.fixture
def output(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'OUTPUT_DIR', tmp_path)
    monkeypatch.setattr(main, 'download_content', Mock())
    return tmp_path


def test_export_deduplicates_and_analyzes_locally(output):
    fake = FakeBrowser()
    report, path = main.run_export('demo', client_factory=lambda **kwargs: fake)
    assert report['content']['count'] == 1
    assert report['content']['items'][0]['metrics']['views'] == 0
    assert report['status'] == 'complete'
    assert report['personality_analysis']['provider'] == 'local_lexicon_v1'
    assert report['personality_analysis']['result']['apertura_a_la_experiencia']['score'] == 75
    assert '_media' not in path.read_text(encoding='utf-8')
    assert ('posts', None) in fake.calls and ('reels', None) in fake.calls


def test_export_keeps_partial_content_after_block(output):
    fake = FakeBrowser()
    fake.collect_media = Mock(return_value=collection_result([{'id': '1', 'code': 'A1'}], 'posts', error='HTTP 429', stopped=True))
    report, path = main.run_export('demo', client_factory=lambda **kwargs: fake)
    assert report['status'] == 'partial'
    fake.collect_media.assert_called_once()
    main.download_content.assert_not_called()
    assert report['content']['collection']['reels']['status'] == 'not_requested'
    assert path.is_file()


def test_benford_shared_profile_is_queried_once_and_files_have_statistics(output):
    fake = FakeBrowser()
    result = main.run_benford_scan('demo', client_factory=lambda **kwargs: fake)
    assert fake.calls.count(('profile', 'shared')) == 1
    assert result['status'] == 'complete'
    assert result['analysis']['followers_of_followers']['sample_size'] == 1
    saved = json.loads((output / 'benford_scan_demo.json').read_text(encoding='utf-8'))
    assert saved['following'][0]['following_count'] == 234
    with (output / 'benford_scan_demo.csv').open(encoding='utf-8-sig', newline='') as handle:
        assert len(list(csv.DictReader(handle))) == 2


def test_benford_block_is_failed_not_success(output):
    fake = FakeBrowser()
    fake.collect_relationship = Mock(return_value=collection_result([], 'users', error='HTTP 429', stopped=True))
    result = main.run_benford_scan('demo', client_factory=lambda **kwargs: fake)
    assert result['status'] == 'failed'
    fake.collect_relationship.assert_called_once()
    assert result['collection']['following']['status'] == 'not_requested'
    assert result['analysis']['followers_of_followers']['chi_square'] is None


def test_benford_keeps_partial_rows_on_cancel(output):
    fake = FakeBrowser()
    fake.collect_relationship = Mock(return_value=collection_result([{'username': 'shared'}], 'users', error='cancelado', stopped=True))
    result = main.run_benford_scan('demo', client_factory=lambda **kwargs: fake)
    assert result['status'] == 'partial'
    assert result['followers'][0]['stats_error']
    assert ('profile', 'shared') not in fake.calls


@pytest.mark.parametrize('limit', [0, -1, True, '10'])
def test_invalid_limit_is_rejected_before_browser(limit, output):
    factory = Mock()
    with pytest.raises(ValueError):
        main.run_export('demo', limit, client_factory=factory)
    factory.assert_not_called()
