from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin
from .throttle import RateLimited


class RateLimitMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        if isinstance(exception, RateLimited):
            response = HttpResponse("Too many requests. Please wait before trying again.", status=429, content_type="text/plain")
            response["Retry-After"] = str(exception.retry_after)
            return response
