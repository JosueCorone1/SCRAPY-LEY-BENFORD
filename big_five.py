"""Transparent local lexical indicators. This is NOT a psychometric model.

The dictionaries below are project-defined examples in Spanish and English,
not a validated inventory. The score is 100 * positive / (positive + opposite)
among matched words, only with at least 100 words, 5 hits and 3 distinct terms.
No text leaves this machine. No trait is scored from absent evidence.
"""
import re
import unicodedata
from collections import Counter

LEXICONS = {
    'apertura_a_la_experiencia': (
        'arte creativo creatividad curiosidad aprender explorar imaginar innovar descubrir ideas art creative curiosity learn explore imagine discover',
        'rutina repeticion costumbre tradicional predecible routine repetition familiar predictable',
    ),
    'responsabilidad': (
        'organizar organizado planificar disciplina puntual cumplir esfuerzo constancia objetivos responsable organized planning discipline punctual reliable goals',
        'desorden descuido posponer improvisar procrastinar desorganizado careless messy postpone procrastinate',
    ),
    'extraversion': (
        'amigos fiesta conversar compartir equipo reunion sociable gente celebrar friends party talk teamwork outgoing celebrate',
        'soledad solitario silencio reservado introspeccion solitude solitary quiet reserved introversion',
    ),
    'amabilidad': (
        'ayudar gracias gratitud colaborar escuchar solidaridad respeto amable compasion empatía help thanks gratitude kindness cooperate empathy',
        'competir rivalidad egoismo discutir pelea competir selfish rivalry argue fight',
    ),
    'neuroticismo': (
        'preocupacion tension nervios estres incertidumbre frustracion worry tension nervous stress uncertainty frustration',
        'calma tranquilidad serenidad relajado estable paciencia calm relaxed peaceful steady patient',
    ),
}
LIMITATIONS = (
    'Indicadores léxicos exploratorios con diccionarios propios ES/EN, sin validación psicométrica. '
    'El índice describe palabras del texto y no mide la personalidad real. No interpreta negaciones, '
    'ironía, citas ni contexto; el tema de una publicación puede cambiar el resultado. '
    'Neuroticismo aquí es el nombre de una dimensión teórica, no un diagnóstico. '
    'No usar para decisiones sobre personas.'
)


def tokens(text):
    normalized = ''.join(char for char in unicodedata.normalize('NFKD', text.casefold())
                         if not unicodedata.combining(char))
    # Links, handles and hashtags are not evidence of a trait.
    normalized = re.sub(r'https?://\S+|[@#]\w+', ' ', normalized)
    return re.findall(r'[a-z]+', normalized)


def analyze_texts(profile, content):
    texts = [profile.get('biography') or ''] + [item.get('caption') or '' for item in content]
    counts = Counter(tokens('\n'.join(texts)))
    total = sum(counts.values())
    result = {'method': 'local_lexicon_v1', 'word_count': total,
              'limitaciones': LIMITATIONS, 'score_meaning': 'Porcentaje de coincidencias del polo positivo entre coincidencias de ambos polos.'}
    for trait, (positive, opposite) in LEXICONS.items():
        pos = {word: counts[word] for word in set(tokens(positive)) if counts[word]}
        neg = {word: counts[word] for word in set(tokens(opposite)) if counts[word]}
        positives, negatives = sum(pos.values()), sum(neg.values())
        hits = positives + negatives
        enough = total >= 100 and hits >= 5 and len(pos) + len(neg) >= 3
        score = round(100 * positives / hits, 1) if enough else None
        result[trait] = {
            'score': score, 'positive_hits': positives, 'opposite_hits': negatives,
            'hits_per_1000_words': round(1000 * hits / total, 2) if total else 0,
            'evidence': {'positive': pos, 'opposite': neg},
            'justificacion': (
                f'{positives} coincidencias del polo positivo y {negatives} del opuesto entre {total} palabras. '
                + ('Índice léxico; no es una puntuación de personalidad.' if enough else
                   'Evidencia insuficiente: se requieren 100 palabras, 5 coincidencias y 3 términos distintos para mostrar un índice.')
            ),
        }
    return result
