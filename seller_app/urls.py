from django.urls import path
from buyer_app import views as shared
from . import views

urlpatterns = [
    path("", views.dashboard, name="seller_dashboard"),
    path("listings/", views.dashboard, name="seller_listings"),
    path("listings/new/", views.edit_listing, name="seller_new"),
    path("listings/<int:product_id>/edit/", views.edit_listing, name="seller_edit"),
    path("listings/<int:product_id>/publish/", views.edit_listing, {"force_publish": True}, name="seller_publish"),
    path("listings/<int:product_id>/withdraw/", views.withdraw, name="seller_withdraw"),
    path("listings/<int:product_id>/revisions/", views.revisions, name="seller_revisions"),
    path("listings/<int:product_id>/revisions/<int:revision_no>/", views.revisions, name="seller_revision"),
    path("listings/<int:product_id>/risk-history/", views.revisions, name="seller_risk_history"),
    path("listings/<int:product_id>/assessment/", views.assessment, name="seller_assessment"),
    path("listings/<int:product_id>/draft-images/<int:position>/", views.draft_image, name="seller_draft_image"),
    path("orders/", shared.orders, {"role": "seller"}, name="seller_orders"),
    path("sales/", shared.orders, {"role": "seller"}, name="seller_sales"),
    path("orders/<int:order_id>/", shared.order_detail, {"role": "seller"}, name="seller_order"),
    path("orders/<int:order_id>/actions/", shared.order_detail, {"role": "seller"}),
    path("conversations/", shared.conversations, {"role": "seller"}, name="seller_conversations"),
    path("conversations/<int:conversation_id>/", shared.conversation_detail, {"role": "seller"}, name="seller_conversation"),
    path("conversations/<int:conversation_id>/messages/", shared.poll_messages, {"role": "seller"}),
    path("conversations/<int:conversation_id>/read/", shared.mark_read, {"role": "seller"}),
]
