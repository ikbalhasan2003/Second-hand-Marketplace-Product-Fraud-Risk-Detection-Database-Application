from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from marketplace.db import actor_transaction, one, rows
from .access import has_role
from .forms import LoginForm, RegistrationForm
from .models import User
from .throttle import throttle


def auth_page(request, app, register=False):
    role = "administrator" if app == "admin" else app
    if register and role == "administrator":
        raise PermissionDenied
    form = (RegistrationForm if register else LoginForm)(request.POST or None)
    if request.method == "POST":
        throttle("registration" if register else "login", request.META.get("REMOTE_ADDR", "unknown"))
        if not register:
            throttle("login", "email:" + request.POST.get("email", "").strip().casefold())
        if form.is_valid():
            data = form.cleaned_data
            if register:
                try:
                    from django.db import transaction
                    with transaction.atomic():
                        record = one("""INSERT INTO users(email,password,full_name,location)
                            VALUES(%s,%s,%s,%s) RETURNING user_id""",
                                     [data["email"], make_password(data["password"]), data["full_name"], data["location"] or None])
                        user = User.objects.get(pk=record["user_id"])
                        with actor_transaction(user):
                            rows("SELECT enable_marketplace_role(%s)", [role])
                    login(request, user, backend="accounts.backends.EmailBackend")
                    return redirect(f"/{app}-app/")
                except IntegrityError:
                    form.add_error("email", "This email already has an account. Please sign in.")
            else:
                user = authenticate(request, username=data["email"], password=data["password"])
                if user and has_role(user, role) and (role != "administrator" or user.status == "active"):
                    login(request, user)
                    target = request.GET.get("next", f"/{app}-app/")
                    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                        target = f"/{app}-app/"
                    return redirect(target)
                form.add_error(None, "Email or password is incorrect, or this account lacks this app's membership.")
    return render(request, "accounts/auth.html", {"form": form, "app": app, "register": register, "title": f"{app.title()} {'registration' if register else 'sign in'}"})


@login_required
@require_POST
def sign_out(request):
    logout(request)
    return redirect("/buyer-app/")


@login_required
def account(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)
        messages.success(request, "Password changed. Other sessions will be invalidated on their next request.")
        return redirect(reverse("account"))
    return render(request, "accounts/account.html", {"form": form, "title": "Account and access"})


@login_required
@require_POST
def enable_role(request, role):
    if role not in ("buyer", "seller") or request.user.status != "active" or has_role(request.user, "administrator"):
        raise PermissionDenied
    with actor_transaction(request.user):
        rows("SELECT enable_marketplace_role(%s)", [role])
    messages.success(request, f"{role.title()} access enabled.")
    return redirect(f"/{role}-app/")
