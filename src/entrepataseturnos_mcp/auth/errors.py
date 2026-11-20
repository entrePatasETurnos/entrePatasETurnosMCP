"""Errors raised by the auth/session layer."""


class SignInRequired(Exception):
    """The caller has no usable API session; they must sign in again."""


class SessionStoreUnavailable(Exception):
    """The shared session store (Redis) could not be reached."""
