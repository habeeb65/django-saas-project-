"""
ASGI config for Mango_project project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Mango_project.settings')

application = get_asgi_application()

# Note: Channels/WebSocket support is disabled.
# To enable real-time notifications via WebSocket:
# 1. pip install channels daphne
# 2. Add 'channels' to INSTALLED_APPS in settings.py
# 3. Set ASGI_APPLICATION = 'Mango_project.asgi.application' in settings.py
# 4. Uncomment and configure the code below:
#
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.auth import AuthMiddlewareStack
# from channels.security.websocket import AllowedHostsOriginValidator
# from notifications.routing import websocket_urlpatterns
#
# application = ProtocolTypeRouter({
#     "http": get_asgi_application(),
#     "websocket": AllowedHostsOriginValidator(
#         AuthMiddlewareStack(
#             URLRouter(websocket_urlpatterns)
#         )
#     ),
# })
