from django.urls import include, path, re_path
from accounts import views
from buyer_app.views import listing_image

urlpatterns = [
    path("listing-media/<path:storage_key>", listing_image, name="listing_image"),
    path("login/", views.auth_page, {"app": "marketplace"}, name="marketplace_login"),
    path("register/", views.auth_page, {"app": "marketplace", "register": True}, name="marketplace_register"),
    path("account/", views.account, name="account"),
    path("account/enable/<str:role>/", views.enable_role, name="enable_role"),
    path("logout/", views.sign_out, name="logout"),
    path("admin-app/login/", views.auth_page, {"app": "admin"}, name="admin_login"),
    path("admin-app/", include("admin_app.urls")),
    path("sell/", include("seller_app.urls")),
    re_path(r"^(?P<legacy_app>buyer|seller)-app/(?P<legacy_path>.*)$", views.legacy_entry),
    path("", include("buyer_app.urls")),
]
