"""Fit labels describe the sample, never whether an account is automated."""
import pytest

import benford
import main


def sample(counts):
    return [digit for digit, count in enumerate(counts, 1) for _ in range(count)]


@pytest.mark.parametrize('counts, code', [
    ([301,176,125,97,79,67,58,51,46], 'compatible'),
    ([276,176,125,97,79,67,58,51,71], 'moderate_deviation'),
    ([100] * 9, 'strong_deviation'),
])
def test_real_distributions_cover_three_fit_levels(counts, code):
    result = benford.analyze_counts(sample(counts))
    assessment = benford.assess_fit(result)
    assert assessment['code'] == code
    assert assessment['automation_verdict'] == 'No determinable con Benford'
    assert assessment['scope'] == 'selected_dataset'


@pytest.mark.parametrize('p, code', [
    (1, 'compatible'), (.05, 'compatible'), (.049999, 'moderate_deviation'),
    (.01, 'moderate_deviation'), (.009999, 'strong_deviation'), (0, 'strong_deviation'),
])
def test_p_value_boundaries(p, code):
    result = benford.analyze_counts(range(1, 1001))
    result['p_value'] = p
    assert benford.assess_fit(result)['code'] == code


@pytest.mark.parametrize('size, code', [(0, 'insufficient_data'), (109, 'insufficient_data'), (110, 'strong_deviation')])
def test_expected_frequency_guard(size, code):
    result = benford.analyze_counts([1] * size)
    assert benford.assess_fit(result)['code'] == code


@pytest.mark.parametrize('complete, interrupted, missing', [
    (False, False, False), (True, True, False), (True, False, True),
])
def test_incomplete_collection_or_metrics_have_no_fit_label(complete, interrupted, missing):
    rows = [{'follower_count': n} for n in range(1, 1001)]
    if missing:
        rows.append({'follower_count': None})
    data = {'followers': rows, 'collection': {'followers': {'complete': complete}, 'metrics_interrupted': interrupted}}
    result = benford.analyze_dataset(data, 'followers', 'follower_count')
    assert result['chi_square'] is not None
    assert result['assessment']['code'] == 'incomplete_data'
    assert main.benford_datasets(data)['followers_of_followers'] == result


def test_zeros_are_excluded_without_being_marked_missing():
    values = sample([301,176,125,97,79,67,58,51,46]) + [0]
    data = {'followers': [{'follower_count': n} for n in values], 'collection': {'followers': {'complete': True}}}
    result = benford.analyze_dataset(data, 'followers', 'follower_count')
    assert result['sample_size'] == 1000
    assert result['assessment']['code'] == 'compatible'
