from .base import *  # noqa: F403
from .base import env

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")  # required in production
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
