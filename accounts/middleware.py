from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from .throttle import RateLimited


class RateLimitMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        if isinstance(exception, RateLimited):
            response = render(request, "429.html", {"title": "Please wait before retrying", "retry_after": exception.retry_after}, status=429)
            response["Retry-After"] = str(exception.retry_after)
            return response
