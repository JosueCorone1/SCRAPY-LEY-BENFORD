"""Playwright extraction through normal navigation and browser-delivered data.

No private endpoint replay, stealth patches, identity rotation or CAPTCHA solving.
The browser and its sync API are owned by one worker thread per operation.
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import urlparse

import config
from . import refs
from .browser_data import (
    collection_result, exact_count, media_from_payload, media_terminal,
    profile_from_payload, relationship_from_payload,
)
from .errors import (
    InstagramBlocked, InstagramGated, InstagramRateLimited, InstagramUpstreamError,
)

SITE = 'https://www.instagram.com'
AUTH_DIR = Path(__file__).resolve().parent.parent / '.auth'
STATE_FILE = AUTH_DIR / 'instagram.json'
COOLDOWN_FILE = AUTH_DIR / 'cooldown.json'
POST_PATH = re.compile(r'^/(?:[A-Za-z0-9._]+/)?(?:p|reel|reels)/([A-Za-z0-9_-]+)/?$')
USER_PATH = re.compile(r'^/([A-Za-z0-9._]+)/?$')
SCROLL_SCRIPT = """element => {
    const candidates = [element, ...element.querySelectorAll('*')];
    const scrollable = candidates.filter(el => el.scrollHeight > el.clientHeight + 10 &&
        ['auto', 'scroll'].includes(getComputedStyle(el).overflowY));
    const target = scrollable.sort((a,b) => b.clientHeight - a.clientHeight)[0];
    if (target) target.scrollTop += Math.max(400, target.clientHeight * .8);
    else window.scrollBy(0, Math.max(500, window.innerHeight * .8));
}"""


class CollectionCancelled(InstagramUpstreamError):
    pass


def _retry_after_seconds(value):
    if not value:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            parsed = parsedate_to_datetime(str(value))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0, (parsed - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def cookies_from_header(raw):
    parsed = SimpleCookie()
    try:
        parsed.load(raw or '')
    except CookieError:
        raise ValueError('INSTAGRAM_COOKIES no tiene formato nombre=valor; nombre=valor.') from None
    if not parsed or 'sessionid' not in parsed:
        raise ValueError('La cookie necesita sessionid. También puedes usar el botón Iniciar sesión.')
    return [{'name': name, 'value': cookie.value, 'domain': '.instagram.com',
             'path': '/', 'secure': True} for name, cookie in parsed.items()]


def cooldown_remaining():
    try:
        until = float(json.loads(COOLDOWN_FILE.read_text(encoding='utf-8'))['until'])
        return max(0.0, until - time.time())
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0


class InstagramBrowser:
    def __init__(self, *, progress=None, cancel=None, login=False):
        self.progress = progress or (lambda message: None)
        self.cancel = cancel
        self.login_mode = login
        self.runtime = self.browser = self.context = self.page = None
        self.halt_error = None
        self.target = ''
        self.phase = None
        self.profiles = {}
        self.media = {}
        self.relationships = {}
        self.allowed_codes = set()
        self.terminal = None
        self.provider_limited = False
        self.structured_relationships = False

    def __enter__(self):
        remaining = cooldown_remaining()
        if remaining:
            raise InstagramRateLimited(f'HTTP 429: quedan {remaining:.0f} s de pausa local. No se abrió otra consulta.')
        cookies = config.instagram_cookies()
        if not self.login_mode and not cookies and not STATE_FILE.is_file():
            raise RuntimeError('Inicia sesión desde el botón de la aplicación o configura INSTAGRAM_COOKIES en .env.')
        # Prefer a project-local browser installation when present.
        local_browsers = Path(__file__).resolve().parent.parent / '.venv' / 'pw-browsers'
        if local_browsers.is_dir():
            os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(local_browsers))
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError('Falta Playwright. Ejecuta python -m pip install -r requirements.txt y python -m playwright install chromium.') from None
        try:
            self.runtime = sync_playwright().start()
            self.browser = self.runtime.chromium.launch(
                headless=False if self.login_mode else config.playwright_headless(),
            )
            options = {'locale': 'en-US', 'viewport': {'width': 1280, 'height': 900}}
            if not self.login_mode and STATE_FILE.is_file():
                options['storage_state'] = str(STATE_FILE)
            self.context = self.browser.new_context(**options)
            if cookies and not self.login_mode and not STATE_FILE.is_file():
                self.context.add_cookies(cookies_from_header(cookies))
            self.context.set_default_timeout(15000)
            self.context.route('**/*', self._route)
            self.page = self.context.new_page()
            self.page.on('response', self._on_response)
            return self
        except Exception as exc:
            self.__exit__(None, None, None)
            if 'Executable doesn' in str(exc):
                raise RuntimeError('Falta Chromium. Ejecuta: python -m playwright install chromium') from None
            raise

    def __exit__(self, *_):
        for resource in (self.context, self.browser):
            if resource:
                try:
                    resource.close()
                except Exception:
                    pass
        if self.runtime:
            self.runtime.stop()

    def _route(self, route):
        if self.halt_error or (self.cancel and self.cancel.is_set()):
            route.abort()
        else:
            route.continue_()

    def _on_response(self, response):
        host = urlparse(response.url).hostname or ''
        if host != 'instagram.com' and not host.endswith('.instagram.com'):
            return
        if response.request.resource_type not in {'document', 'xhr', 'fetch'}:
            return
        if response.status == 429:
            delay = _retry_after_seconds(response.headers.get('retry-after'))
            if delay is None:
                delay = config.INSTAGRAM_RATE_LIMIT_COOLDOWN_SECONDS
            delay = max(delay, cooldown_remaining())
            self.halt_error = InstagramRateLimited(
                f'Instagram limitó las solicitudes (HTTP 429). Espera al menos {delay:.0f} s; '
                'el bloqueo del servidor puede durar más. No se harán más consultas.'
            )
            try:
                AUTH_DIR.mkdir(parents=True, exist_ok=True)
                COOLDOWN_FILE.write_text(json.dumps({'until': time.time() + delay}), encoding='utf-8')
            except OSError:
                pass
            return
        if response.status in (401, 403) and not self.login_mode:
            self.halt_error = (InstagramGated('Instagram requiere una sesión válida (HTTP 401).')
                               if response.status == 401 else InstagramBlocked('Instagram bloqueó la consulta (HTTP 403).'))
            return
        if self.halt_error or self.login_mode or response.status != 200:
            return
        if 'json' in response.headers.get('content-type', ''):
            try:
                payload = response.json()
            except Exception:
                return
            self._consume(payload, response.url)

    def _consume(self, payload, response_url=''):
        if not self.target:
            return
        profile = profile_from_payload(payload, self.target)
        if profile:
            self.profiles.setdefault(self.target, {}).update(profile)
        if self.phase in {'posts', 'reels', 'detail'}:
            self.media.update(media_from_payload(payload, self.target, self.allowed_codes))
            if self.phase != 'detail':
                terminal = media_terminal(payload, self.phase)
                if terminal is not None:
                    self.terminal = terminal
        elif self.phase in {'followers', 'following'}:
            target_id = self.profiles.get(self.target, {}).get('id')
            rows, terminal, limited = relationship_from_payload(payload, self.phase, response_url, target_id)
            self.relationships.update(rows)
            self.structured_relationships |= bool(rows) or terminal is not None
            if terminal is not None:
                self.terminal = terminal
            self.provider_limited |= limited

    def _check(self):
        if self.halt_error:
            raise self.halt_error
        if self.cancel and self.cancel.is_set():
            raise CollectionCancelled('Recopilación cancelada por el usuario; se conservan los datos obtenidos.')
        if not self.login_mode and self.page:
            path = urlparse(self.page.url).path
            if any(marker in path for marker in ('/accounts/login', '/challenge/', '/checkpoint/')):
                self.halt_error = InstagramGated('Instagram solicita iniciar sesión o verificarla en el navegador.')
                raise self.halt_error

    def _wait(self, seconds=None):
        seconds = config.INSTAGRAM_REQUEST_INTERVAL_SECONDS if seconds is None else seconds
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._check()
            self.page.wait_for_timeout(min(200, max(1, (deadline - time.monotonic()) * 1000)))
        self._check()

    def _embedded(self):
        scripts = self.page.locator('script[type="application/json"]').all_text_contents()
        for script in scripts:
            if len(script) > 8_000_000:
                continue
            try:
                self._consume(json.loads(script))
            except (ValueError, TypeError):
                continue

    def _navigate(self, path):
        self._check()
        try:
            response = self.page.goto(SITE + path, wait_until='domcontentloaded', timeout=45000)
            self._wait()
            if response is not None and response.status >= 400:
                raise InstagramUpstreamError(f'No se pudo abrir la página (HTTP {response.status}).')
        except Exception:
            self._check()
            raise
        self._embedded()
        self._check()

    def get_profile(self, user):
        username = user.get('username')
        if not username:
            raise ValueError('Playwright necesita el nombre de usuario, no solo el ID.')
        username = username.casefold()
        self._check()
        if username in self.profiles and self.profiles[username].get('_visited'):
            return dict(self.profiles[username])
        self.target, self.phase = username, 'profile'
        self.progress(f'Playwright: leyendo perfil @{username}...')
        self._navigate(f'/{username}/')
        profile = self.profiles.get(username, {})
        header = self.page.locator('header').first
        if header.count():
            for kind, field in (('followers', 'follower_count'), ('following', 'following_count')):
                if profile.get(field) is not None:
                    continue
                link = header.locator(f'a[href$="/{kind}/"]').first
                if link.count():
                    titles = link.locator('[title]').evaluate_all('(els) => els.map(el => el.title)')
                    texts = titles + [link.inner_text().split('\n')[0].split(' ')[0]]
                    profile[field] = next((exact_count(text) for text in texts if exact_count(text) is not None), None)
        if not any(value is not None for value in profile.values()):
            raise InstagramUpstreamError('No se pudo leer el perfil. La página puede estar restringida o haber cambiado de formato.')
        profile.update({'username': username, 'link': f'{SITE}/{username}/', '_visited': True})
        self.profiles[username] = profile
        return dict(profile)

    def _post_links(self):
        links = self.page.locator('main a[href]').evaluate_all('(els) => els.map(el => el.getAttribute("href"))')
        found = {}
        for href in links:
            path = urlparse(href).path
            match = POST_PATH.fullmatch(path)
            if match:
                found[match[1]] = path
        return found

    def collect_media(self, user, kind, limit=None):
        rows, links = {}, {}
        self.target = user['username'].casefold()
        self.phase, self.media, self.allowed_codes = kind, {}, set()
        self.terminal = None
        complete = limited = stopped = False
        error = None
        try:
            suffix = 'reels/' if kind == 'reels' else ''
            self._navigate(f'/{self.target}/{suffix}')
            idle = 0
            for turn in range(config.playwright_max_scrolls()):
                before = len(links)
                links.update(self._post_links())
                self.allowed_codes.update(links)
                self._embedded()
                # Include only posts authored by the target, captured from this view.
                for code, item in self.media.items():
                    if kind == 'reels' and item.get('product_type') not in {'clips', 'reel'} and code not in links:
                        continue
                    links.setdefault(code, f'/reel/{code}/' if kind == 'reels' else f'/p/{code}/')
                total = self.profiles.get(self.target, {}).get('post_count') if kind == 'posts' else None
                self.progress(f'Playwright: {len(links)} enlaces de {kind} encontrados.')
                if self.terminal is True or (total is not None and len(links) >= total):
                    complete = True
                    break
                if limit is not None and len(links) >= limit:
                    limited = True
                    break
                idle = idle + 1 if len(links) == before else 0
                if idle >= 3:
                    error = 'La página dejó de cargar contenido; no se pudo confirmar el final de la lista.'
                    break
                self.page.locator('body').evaluate(SCROLL_SCRIPT)
                self._wait()
            else:
                error = 'Se alcanzó el máximo de desplazamientos; extracción parcial.'
            selected = list(links.items())[:limit]
            if len(selected) < len(links):
                limited, complete = True, False
            # A detail navigation obtains captions, video URLs and carousel metadata.
            for index, (code, path) in enumerate(selected, 1):
                self._check()
                self.phase = 'detail'
                self.allowed_codes = {code}
                self.progress(f'Playwright: leyendo {kind} {index}/{len(selected)}...')
                self._navigate(path)
                item = self.media.get(code)
                if item:
                    rows[code] = item
                else:
                    error = 'No se pudieron leer los detalles de uno o más contenidos; no se inventaron textos ni métricas.'
                    complete = False
        except Exception as exc:
            stopped = isinstance(exc, (InstagramBlocked, InstagramGated, CollectionCancelled))
            error = str(exc)[:500]
            complete = False
        # Preserve already captured payloads even if a later navigation was blocked.
        for code in list(links)[:limit]:
            if code in self.media:
                rows.setdefault(code, self.media[code])
        return collection_result(list(rows.values()), kind, complete=complete and not error,
                                 limited=limited and not error, error=error, stopped=stopped)

    def collect_relationship(self, user, kind, limit=None):
        self.relationships = {}
        self.structured_relationships = False
        dom_rows = {}
        self.terminal = None
        self.provider_limited = False
        complete = limited = stopped = False
        error = None
        try:
            profile = self.get_profile(user)
            self.target, self.phase = user['username'].casefold(), kind
            self._navigate(f'/{self.target}/')
            expected = profile.get('follower_count' if kind == 'followers' else 'following_count')
            if expected == 0:
                return collection_result([], 'users', complete=True)
            self.page.locator(f'header a[href$="/{kind}/"]').first.click()
            self._wait()
            dialog = self.page.get_by_role('dialog').last
            dialog.wait_for(state='visible')
            idle = 0
            previous_count = -1
            for turn in range(config.playwright_max_scrolls()):
                # DOM fallback is scoped to the actual relationship dialog.
                anchors = dialog.locator('a[href]').evaluate_all(
                    '(els) => els.map(el => ({href: el.getAttribute("href"), text: el.innerText}))'
                )
                for anchor in anchors:
                    match = USER_PATH.fullmatch(urlparse(anchor['href']).path)
                    if match and match[1].casefold() not in {self.target, 'accounts', 'explore', 'reels', 'direct', 'stories'}:
                        username = match[1].casefold()
                        dom_rows.setdefault(username, {
                            'username': username, 'link': f'{SITE}/{username}/',
                            'follower_count': None, 'following_count': None,
                        })
                visible_rows = self.relationships if self.structured_relationships else dom_rows
                self.progress(f'Playwright: {len(visible_rows)} {kind} visibles.')
                if self.provider_limited:
                    error = 'Instagram indicó que esta lista tiene visibilidad limitada.'
                    break
                if self.terminal is True or (self.structured_relationships and expected is not None and len(visible_rows) >= expected):
                    complete = self.structured_relationships
                    break
                if self.structured_relationships and limit is not None and len(visible_rows) >= limit:
                    limited = True
                    break
                idle = idle + 1 if len(visible_rows) == previous_count else 0
                previous_count = len(visible_rows)
                if idle >= 3:
                    error = 'La lista dejó de cargar; no se pudo confirmar que estén todas las cuentas.'
                    break
                dialog.evaluate(SCROLL_SCRIPT)
                self._wait()
            else:
                error = 'Se alcanzó el máximo de desplazamientos; lista parcial.'
        except Exception as exc:
            stopped = isinstance(exc, (InstagramBlocked, InstagramGated, CollectionCancelled))
            error = str(exc)[:500]
            complete = False
        if not self.structured_relationships and dom_rows:
            # Suggestions may appear in the same dialog. Do not silently treat
            # DOM-only usernames as confirmed membership for a Benford sample.
            error = error or 'No se pudo confirmar qué filas pertenecen a la lista. Se omiten candidatos DOM para evitar incluir sugerencias.'
            complete = False
        rows = list(self.relationships.values())
        if limit is not None and len(rows) > limit:
            rows, limited, complete = rows[:limit], True, False
        return collection_result(rows, 'users', complete=complete and not error,
                                 limited=limited and not error, error=error, stopped=stopped)


def login_session(*, progress=None, cancel=None):
    """Let the user enter credentials/2FA directly in a visible browser."""
    with InstagramBrowser(progress=progress, cancel=cancel, login=True) as session:
        session.progress('Inicia sesión en el navegador. Tienes 5 minutos; completa allí cualquier verificación.')
        session._navigate('/accounts/login/')
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            session._check()
            cookies = session.context.cookies(SITE)
            if any(cookie['name'] == 'sessionid' and cookie['value'] for cookie in cookies):
                path = urlparse(session.page.url).path
                if not any(part in path for part in ('/accounts/login', '/challenge', '/checkpoint')):
                    AUTH_DIR.mkdir(parents=True, exist_ok=True)
                    session.context.storage_state(path=str(STATE_FILE))
                    return STATE_FILE
            session._wait(0.5)
        raise TimeoutError('No se completó el inicio de sesión en 5 minutos. Puedes volver a abrirlo.')
