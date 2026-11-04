from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard), path("review-queue/", views.queue),
    path("reviews/", views.queue), path("reviews/<int:product_id>/", views.case),
    path("reviews/orders/<int:order_id>/", views.dispute),
    path("cases/<int:product_id>/", views.case), path("disputes/<int:order_id>/", views.dispute),
    path("models/", views.models), path("models/<int:model_id>/", views.models),
    path("rulesets/", views.models), path("rulesets/new/", views.ruleset_new), path("rulesets/<int:ruleset_id>/", views.models),
    path("audit-log/", views.audit_log), path("audit-log/<int:audit_id>/", views.audit_log),
    path("exports/", views.exports), path("exports/<int:dataset_id>/", views.exports),
    path("exports/<int:dataset_id>/download/", views.export_download),
]
