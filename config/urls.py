from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.urls import include, path
from accounts import views

urlpatterns = [
    path("", lambda request: redirect("/buyer-app/")),
    path("account/", views.account, name="account"),
    path("account/enable/<str:role>/", views.enable_role, name="enable_role"),
    path("logout/", views.sign_out, name="logout"),
]
for app in ("buyer", "seller", "admin"):
    urlpatterns += [path(f"{app}-app/login/", views.auth_page, {"app": app}, name=f"{app}_login")]
    if app != "admin":
        urlpatterns += [path(f"{app}-app/register/", views.auth_page, {"app": app, "register": True}, name=f"{app}_register")]
    urlpatterns += [path(f"{app}-app/", include(f"{app}_app.urls"))]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
