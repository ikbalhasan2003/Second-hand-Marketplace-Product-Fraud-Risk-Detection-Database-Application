from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import never_cache


def has_role(user, role):
    return user.is_authenticated and user.is_active and user.groups.filter(name=role).exists()


def require_role(role, active=False):
    def decorator(view):
        @wraps(view)
        @login_required(login_url=f"/{'admin' if role == 'administrator' else role}-app/login/")
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, role) or (active and request.user.status != "active"):
                raise PermissionDenied("This action requires the appropriate active membership.")
            if role == "administrator" and request.user.status != "active":
                raise PermissionDenied("An active administrator is required.")
            return view(request, *args, **kwargs)
        # Admin responses include private reports, decisions and dataset metadata.
        return never_cache(wrapped) if role == "administrator" else wrapped
    return decorator
