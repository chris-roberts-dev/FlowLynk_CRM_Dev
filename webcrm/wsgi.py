"""
WSGI config for FlowLynk.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webcrm.settings.dev")

application = get_wsgi_application()
