# https://docs.djangoproject.com/en/1.10/ref/settings/

import os

from decouple import config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def base_dir_join(*args):
    return os.path.join(BASE_DIR, *args)


SITE_ID = 1

DEBUG = True

ADMINS = (
    ('Admin', 'foo@example.com'),
)

AUTH_USER_MODEL = 'root.User'

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'whitenoise.runserver_nostatic',
    'django_countries',
    'django_js_reverse',
    'webpack_loader',
    'widget_tweaks',

    'root',
    'koe'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'root.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [base_dir_join('templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'koe.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-nz'

TIME_ZONE = 'Pacific/Auckland'

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATICFILES_DIRS = (
    base_dir_join('assets'),
)

# Webpack
WEBPACK_LOADER = {
    'DEFAULT': {
        'CACHE': False,  # on DEBUG should be False
        'BUNDLE_DIR_NAME': 'bundles/',  # must end with slash
        'STATS_FILE': base_dir_join('webpack-stats.json'),
        'POLL_INTERVAL': 0.1,
        'IGNORE': ['.+\.hot-update.js', '.+\.map']
    },
    'JQUERY': {
        'BUNDLE_DIR_NAME': 'bundles/',
        'STATS_FILE': 'jquery-webpack-stats.json',
    }
}

# Celery
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

MAX_FILE_NAME_LENGTH = 20
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# Redis cache
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': '{0}:{1}'.format(config('REDIS_HOST'), config('REDIS_PORT')),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            'PASSWORD': config('REDIS_PASSWORD'),
            'IGNORE_EXCEPTIONS': True,
            'DB': 1
        }
    }
}
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

LOGIN_URL = '/login'

# site configuration
SITE_URL = os.getenv('SITE_URL', 'http://127.0.0.1:8000/')
SITE_URL_BARE = SITE_URL[:-1]
assert SITE_URL.endswith('/'), 'SITE_URL must have trailing /'

_email_config = os.getenv('EMAIL_CONFIG', 'console')
if _email_config == 'console':
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
elif _email_config == 'naomi':
    INSTALLED_APPS += ('naomi',)
    EMAIL_BACKEND = 'naomi.mail.backends.naomi.NaomiBackend'
    EMAIL_FILE_PATH = base_dir_join('tmp_email')
else:  # assume we have fully-specified smtp configuration
    email_host, email_user, email_pass, email_port = _email_config.split(':', 3)
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = email_host
    EMAIL_HOST_USER = email_user
    EMAIL_HOST_PASSWORD = email_pass
    EMAIL_TIMEOUT = 10  # hopefully this is enough...
    EMAIL_PORT = email_port
    EMAIL_USE_TLS = True
    FROM_EMAIL = os.getenv('FROM_EMAIL')


SIGN_UP_SECRET = '66e712a'
