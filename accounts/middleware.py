from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from .throttle import RateLimited


class RateLimitMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # Authenticated marketplace pages contain participant-only records and
        # identity-specific navigation; shared caches must never retain them.
        if getattr(request, "user", None) and request.user.is_authenticated:
            response["Cache-Control"] = "private, no-store"
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, RateLimited):
            response = render(request, "429.html", {"title": "Please wait before retrying", "retry_after": exception.retry_after}, status=429)
            response["Retry-After"] = str(exception.retry_after)
            return response
