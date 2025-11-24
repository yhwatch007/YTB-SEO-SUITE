"""
Django settings for core project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import environ

# Load environment variables
load_dotenv()
env = environ.Env()
environ.Env.read_env()

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Security
SECRET_KEY = 'django-insecure-%d=#izd#+tse^c^rl1vds=_vfc#y!60lkexd#o(jeuyrjk1f$='

# IMPORTANT: Set DEBUG to False in production via environment variable
DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

# FIXED: Removed https:// and trailing slashes
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "iot.yahyz.news",
    "www.iot.yahyz.news",
    "web-production-4a5f.up.railway.app",
    ".railway.app",  # Allow any Railway subdomain
]

# FIXED: Removed trailing slashes
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1",
    "http://localhost",
    "https://iot.yahyz.news",
    "https://www.iot.yahyz.news",
    "https://web-production-4a5f.up.railway.app",
]

# Railway proxy settings
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'web',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# API Keys
YOUTUBE_API_KEY = env("YOUTUBE_API_KEY", default="")
YOUTUBE_DEFAULT_REGION = env("YOUTUBE_DEFAULT_REGION", default="US")
GOOGLE_API_KEY = env("GOOGLE_API_KEY", default="")