from django.urls import path
from . import views

urlpatterns = [
    path("", views.catalog), path("listings/", views.catalog, name="catalog"),
    path("listings/<int:product_id>/", views.listing_detail),
    path("listings/<int:product_id>/revisions/<int:revision_no>/", views.listing_detail),
    path("listings/<int:product_id>/orders/", views.purchase),
    path("listings/<int:product_id>/conversations/", views.start_conversation),
    path("listings/<int:product_id>/reports/new/", views.report_new),
    path("listings/<int:product_id>/reports/", views.report_new),
    path("orders/", views.orders), path("orders/<int:order_id>/", views.order_detail),
    path("orders/<int:order_id>/actions/", views.order_detail),
    path("conversations/", views.conversations),
    path("conversations/<int:conversation_id>/", views.conversation_detail),
    path("conversations/<int:conversation_id>/messages/", views.poll_messages),
    path("conversations/<int:conversation_id>/read/", views.mark_read),
    path("reports/", views.reports), path("reports/<int:report_id>/", views.report_detail),
    path("reports/<int:report_id>/evidence/", views.append_evidence),
    path("evidence/<int:attachment_id>/", views.evidence),
]
