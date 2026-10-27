import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
import gemini_analysis as g
import main

PROFILE = {'biography': 'Me gusta aprender y explorar ideas. ' * 20, 'username': 'no_enviar', 'cookies': 'no_enviar'}
CONTENT = [{'caption': 'Organizo mis proyectos con tiempo y disciplina. ' * 20, 'url': 'https://no-enviar.test', 'media': 'no_enviar'}]


def answer():
    return {k: {'score': 60, 'confidence': 'baja', 'justificacion': 'Estimación de ejemplo de prueba.',
        'evidence': [{'source_id': 'bio', 'quote': 'Me gusta aprender'},
                     {'source_id': 'contenido_1', 'quote': 'Organizo mis proyectos'}]} for k in g.TRAITS}


def client_for(text=None, error=None):
    factory = MagicMock()
    generate = factory.return_value.__enter__.return_value.models.generate_content
    generate.return_value = SimpleNamespace(text=text)
    generate.side_effect = error
    return factory, generate


def test_missing_key_does_not_call_or_fake_analysis():
    factory, call = client_for()
    result = g.analyze_profile(PROFILE, CONTENT, client_factory=factory)
    assert result['status'] == 'not_configured' and result['result'] is None
    factory.assert_not_called()


def test_success_sends_only_text_and_validates_sdk_config(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-only')
    factory, call = client_for(json.dumps(answer()))
    result = g.analyze_profile(PROFILE, CONTENT, client_factory=factory)
    assert result['status'] == 'complete'
    assert result['result']['neuroticismo']['score'] == 60
    args = call.call_args.kwargs
    assert 'no_enviar' not in args['contents'] and 'no-enviar' not in args['contents']
    assert set(json.loads(args['contents'])) == {'sources'}
    assert args['config'].response_mime_type == 'application/json'
    assert factory.call_args.kwargs['http_options'].retry_options.attempts == 1
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize('text', ['no json', '{}', '', 'null'])
def test_invalid_model_output_is_explicit(monkeypatch, text):
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-only')
    factory, _ = client_for(text)
    assert g.analyze_profile(PROFILE, CONTENT, client_factory=factory)['status'] == 'invalid_response'


@pytest.mark.parametrize('code', [400, 401, 403, 404, 429, 500])
def test_api_errors_do_not_leak_key(monkeypatch, code):
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-secret')
    error = RuntimeError('synthetic-secret')
    error.code = code
    factory, _ = client_for(error=error)
    result = g.analyze_profile(PROFILE, CONTENT, client_factory=factory)
    assert result['status'] == 'api_error'
    assert 'synthetic-secret' not in json.dumps(result)


@pytest.mark.parametrize('score', [-1, 101, True, float('nan'), '80'])
def test_out_of_range_score_rejected(score):
    raw = answer()
    raw[g.TRAITS[0]]['score'] = score
    with pytest.raises(ValueError):
        g.validate_result(raw, g.prepare_sources(PROFILE, CONTENT)[0])


def test_invented_quote_rejected():
    raw = answer()
    raw[g.TRAITS[0]]['evidence'][0]['quote'] = 'Una frase que no existe'
    with pytest.raises(ValueError):
        g.validate_result(raw, g.prepare_sources(PROFILE, CONTENT)[0])


def test_single_source_scores_are_null():
    raw = answer()
    for entry in raw.values():
        entry['evidence'] = entry['evidence'][:1]
    result = g.validate_result(raw, g.prepare_sources(PROFILE, CONTENT)[0])
    assert all(result[k]['score'] is None for k in g.TRAITS)


def test_insufficient_text_skips_api(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-only')
    factory, _ = client_for()
    assert g.analyze_profile({'biography': 'Hola'}, [], client_factory=factory)['status'] == 'insufficient_evidence'
    factory.assert_not_called()


def test_input_is_bounded_and_links_removed():
    sources, truncated = g.prepare_sources({'biography': '@persona https://example.org ' + 'a' * 150}, [], max_chars=100)
    assert truncated and len(sources[0]['text']) == 100
    assert '@' not in sources[0]['text'] and 'https' not in sources[0]['text']


def test_reanalysis_preserves_original_and_saves_missing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'OUTPUT_DIR', tmp_path)
    original = tmp_path / 'instagram_report_demo.json'
    original.write_text(json.dumps({'profile': PROFILE, 'content': {'items': CONTENT}, 'status': 'complete'}), encoding='utf-8')
    before = original.read_bytes()
    new = main.reanalyze_saved_report('demo')
    assert new.name.endswith('_gemini.json') and original.read_bytes() == before
    assert json.loads(new.read_text())['personality_analysis']['status'] == 'not_configured'


def test_official_sdk_serializes_request_with_mock_http(monkeypatch):
    import httpx
    from google import genai
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-only')
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        assert request.url.host == 'generativelanguage.googleapis.com'
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model',
            'parts': [{'text': json.dumps(answer())}]}, 'finishReason': 'STOP'}]})
    def factory(**kwargs):
        kwargs['http_options'] = kwargs['http_options'].model_copy(update={
            'client_args': {'transport': httpx.MockTransport(handler)}})
        return genai.Client(**kwargs)
    result = g.analyze_profile(PROFILE, CONTENT, client_factory=factory)
    assert result['status'] == 'complete'
    assert len(seen) == 1 and seen[0]['generationConfig']['responseMimeType'] == 'application/json'
