"""Synthetic examples for a reproducible offline GUI demonstration."""
from big_five import analyze_texts
from main import benford_datasets


def examples():
    rows = []
    for digit, count in enumerate([301, 176, 125, 97, 79, 67, 58, 51, 46], 1):
        for index in range(count):
            rows.append({'username': f'simulado_{digit}_{index:03}', 'full_name': 'Perfil sintético',
                         'follower_count': digit * 100 + index % 100,
                         'following_count': digit * 1000 + index % 100,
                         'is_private': False, 'is_verified': False})
    scan = {'target': 'DEMOSTRACION_SINTETICA', 'status': 'demo', 'followers': rows, 'following': rows,
            'collection': {'followers': {'complete': True}, 'following': {'complete': True}, 'metrics_interrupted': False}}
    scan['analysis'] = benford_datasets(scan)
    profile = {'username': 'DEMOSTRACION_SINTETICA', 'full_name': 'Datos de prueba, no Instagram',
               'biography': 'arte creativo aprender rutina ' * 30, 'counts': {'followers': 1000, 'following': 1000}}
    report = {'target': 'DEMOSTRACION_SINTETICA', 'status': 'demo', 'profile': profile,
              'content': {'items': [], 'requested_limit': None, 'collection': {}},
              'personality_analysis': {'status': 'local_exploratory', 'result': analyze_texts(profile, [])}}
    return report, scan
