from django.urls import path
from django.shortcuts import render
from accounts.access import require_role

urlpatterns = [path("", require_role("administrator")(lambda request: render(request, "foundation.html", {"title": "Admin App"})))]
