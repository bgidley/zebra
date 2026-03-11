"""Django settings for zebra-agent-web project.

This is a focused agent-only version of zebra-web, supporting only
agent workflows and not standalone workflow management.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / ".env")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-dev-only-change-in-production-zebra-agent"
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# In DEBUG mode, allow all hosts for easier development (e.g., Tailscale access)
if DEBUG:
    ALLOWED_HOSTS = ["*"]

# Application definition
INSTALLED_APPS = [
    "daphne",  # ASGI server, must be first for channels
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "channels",
    "zebra_agent_web.api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "zebra_agent_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

# ASGI application (for channels/websockets)
ASGI_APPLICATION = "zebra_agent_web.asgi.application"

# Channel layers for WebSocket support
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# For production, use Redis:
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels_redis.core.RedisChannelLayer",
#         "CONFIG": {
#             "hosts": [("127.0.0.1", 6379)],
#         },
#     },
# }

# Database Configuration
# This Django application uses Django ORM for all data persistence:
# - Workflow state (ProcessInstance, TaskInstance, FlowOfExecution)
# - Metrics (WorkflowRun, TaskExecution)
# - Process definitions
#
# The DjangoStore and DjangoMetricsStore implementations use these models
# defined in zebra_agent_web/api/models.py
#
# Configure your preferred database backend below (Oracle, PostgreSQL, SQLite, etc.)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.oracle",
        "NAME": os.environ.get("ORACLE_DSN", ""),
        "USER": os.environ.get("ORACLE_USERNAME", ""),
        "PASSWORD": os.environ.get("ORACLE_PASSWORD", ""),
    }
}

# Alternative configurations:
# PostgreSQL:
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": os.environ.get("PGDATABASE", "zebra"),
#         "USER": os.environ.get("PGUSER", "zebra"),
#         "PASSWORD": os.environ.get("PGPASSWORD", ""),
#         "HOST": os.environ.get("PGHOST", "localhost"),
#         "PORT": os.environ.get("PGPORT", "5432"),
#     }
# }
#
# SQLite (development):
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "EXCEPTION_HANDLER": "zebra_agent_web.api.exceptions.custom_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# CORS settings - permissive for development
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # Vite dev server
    "http://127.0.0.1:3000",
]

# Zebra Agent settings
# Storage is handled by Django ORM (see DATABASES config above)
ZEBRA_AGENT_SETTINGS = {
    "LIBRARY_PATH": os.environ.get("ZEBRA_LIBRARY_PATH", "~/.zebra/workflows"),
    "LLM_PROVIDER": os.environ.get("ZEBRA_LLM_PROVIDER", "anthropic"),
    "LLM_MODEL": os.environ.get("ZEBRA_LLM_MODEL", None),
}

# Logging
LOG_DIR = BASE_DIR / "tmp"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file_zebra": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "zebra.log",
            "maxBytes": 5 * 1024 * 1024,  # 5 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
        "file_django": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "django.log",
            "maxBytes": 5 * 1024 * 1024,  # 5 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file_django"],
        "level": "INFO",
    },
    "loggers": {
        "zebra_agent_web": {
            "handlers": ["console", "file_zebra"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "zebra_agent": {
            "handlers": ["console", "file_zebra"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "zebra": {
            "handlers": ["console", "file_zebra"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "django": {
            "handlers": ["console", "file_django"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file_django"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
