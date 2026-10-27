"""Shared errors for the browser extractor; no network clients."""


class InstagramUpstreamError(Exception):
    pass


class InstagramGated(InstagramUpstreamError):
    pass


class InstagramBlocked(InstagramUpstreamError):
    pass


class InstagramRateLimited(InstagramBlocked):
    pass
