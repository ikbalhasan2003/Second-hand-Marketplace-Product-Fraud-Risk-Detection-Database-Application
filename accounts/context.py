def marketplace_context(request):
    roles = set(request.user.groups.values_list("name", flat=True)) if request.user.is_authenticated else set()
    shell = "seller" if request.path.startswith(("/sell/", "/seller-app/")) else "admin" if request.path.startswith("/admin-app/") else "buyer"
    return {"can_buy": "buyer" in roles, "can_sell": "seller" in roles, "can_admin": "administrator" in roles, "shell": shell}
