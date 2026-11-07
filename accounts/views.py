import secrets
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from marketplace.db import actor_transaction, one, rows
from .access import has_role
from .forms import LoginForm, ProfileForm, RegistrationForm, SellerOnboardingForm
from .models import User
from .throttle import throttle


def auth_page(request, app, register=False):
    role = "administrator" if app == "admin" else app
    if app == "marketplace":
        role = (request.POST.get("role", "buyer") if request.method == "POST" else request.GET.get("role", "buyer")) if register else None
        if register and role not in ("buyer", "seller"):
            raise PermissionDenied
    destination = "/admin-app/" if app == "admin" else "/sell/" if role == "seller" else "/"
    if register and role == "administrator":
        raise PermissionDenied
    form = RegistrationForm(request.POST or None, seller=role == "seller") if register else LoginForm(request.POST or None)
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
                        record = one("""INSERT INTO users(email,password,full_name,location,private_contact)
                            VALUES(%s,%s,%s,%s,%s) RETURNING user_id""",
                                     [data["email"], make_password(data["password"]), data.get("full_name") or "Member " + secrets.token_hex(4), data.get("location") or None, data.get("private_contact") or None])
                        user = User.objects.get(pk=record["user_id"])
                        with actor_transaction(user):
                            rows("SELECT enable_marketplace_role(%s)", [role])
                    login(request, user, backend="accounts.backends.EmailBackend")
                    return redirect(destination)
                except IntegrityError:
                    form.add_error("email", "This email already has an account. Please sign in.")
            else:
                user = authenticate(request, username=data["email"], password=data["password"])
                if user and (has_role(user, role) if role else (has_role(user, "buyer") or has_role(user, "seller"))) and (role != "administrator" or user.status == "active"):
                    if not role and has_role(user, "seller") and not has_role(user, "buyer"):
                        destination = "/sell/"
                    login(request, user)
                    target = request.GET.get("next", destination)
                    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                        target = destination
                    return redirect(target)
                form.add_error(None, "Email or password is incorrect, or this account lacks the required membership.")
    return render(request, "accounts/auth.html", {"form": form, "app": app, "register": register, "title": f"{app.title()} {'registration' if register else 'sign in'}"})


@login_required
@require_POST
def sign_out(request):
    logout(request)
    return redirect("/")


@login_required
def account(request):
    profile_action = request.method == "POST" and request.POST.get("action") == "profile"
    profile_form = ProfileForm(request.POST if profile_action else None, prefix="profile",
                               seller=has_role(request.user, "seller"),
                               initial={key: getattr(request.user, key) for key in ("full_name", "location", "private_contact")})
    form = PasswordChangeForm(request.user, request.POST if request.method == "POST" and not profile_action else None)
    if profile_action and profile_form.is_valid():
        with actor_transaction(request.user, "Member updated own profile"):
            previous = one("SELECT location FROM users WHERE user_id=%s FOR UPDATE", [request.user.pk])
            rows("UPDATE users SET full_name=%s,location=%s,private_contact=%s WHERE user_id=%s",
                 [profile_form.cleaned_data["full_name"], profile_form.cleaned_data["location"] or None,
                  profile_form.cleaned_data["private_contact"] or None, request.user.pk])
            if previous["location"] != (profile_form.cleaned_data["location"] or None):
                # Seller location is a model input. Preserve old assessment/order
                # evidence and enqueue fresh contexts through the existing trigger.
                rows("SELECT product_id FROM products WHERE seller_id=%s ORDER BY product_id FOR UPDATE", [request.user.pk])
                rows("UPDATE products SET context_version=context_version+1 WHERE seller_id=%s", [request.user.pk])
        messages.success(request, "Profile updated.")
        return redirect(reverse("account"))
    if request.method == "POST" and not profile_action and form.is_valid():
        user = form.save(commit=False)
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)
        messages.success(request, "Password changed. Other sessions will be invalidated on their next request.")
        return redirect(reverse("account"))
    response = render(request, "accounts/account.html", {"form": form, "profile_form": profile_form, "title": "Account and access"})
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def enable_role(request, role):
    if role not in ("buyer", "seller") or request.user.status != "active" or has_role(request.user, "administrator"):
        raise PermissionDenied
    if request.method not in ("GET", "POST"):
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["GET", "POST"])
    if role == "seller":
        form = SellerOnboardingForm(request.POST if request.method == "POST" else None,
                                    initial={key: getattr(request.user, key) for key in ("full_name", "location", "private_contact")})
        if request.method != "POST" or not form.is_valid():
            return render(request, "accounts/onboarding.html", {"form": form, "title": "Become a seller"})
    elif request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    with actor_transaction(request.user):
        if role == "seller":
            previous = one("SELECT location FROM users WHERE user_id=%s FOR UPDATE", [request.user.pk])
            rows("UPDATE users SET full_name=%s,location=%s,private_contact=%s WHERE user_id=%s",
                 [form.cleaned_data["full_name"], form.cleaned_data["location"], form.cleaned_data["private_contact"], request.user.pk])
            if previous["location"] != form.cleaned_data["location"]:
                rows("SELECT product_id FROM products WHERE seller_id=%s ORDER BY product_id FOR UPDATE", [request.user.pk])
                rows("UPDATE products SET context_version=context_version+1 WHERE seller_id=%s", [request.user.pk])
        rows("SELECT enable_marketplace_role(%s)", [role])
    messages.success(request, f"{role.title()} access enabled.")
    return redirect("/sell/" if role == "seller" else "/")


def legacy_entry(request, legacy_app, legacy_path):
    """Redirect bookmarks only; execute unsafe requests once with original body/CSRF."""
    prefix = "/sell/" if legacy_app == "seller" else "/"
    target = prefix + legacy_path
    auth = legacy_path in ("login/", "register/")
    if auth:
        target = "/" + legacy_path
    if not auth:
        match = resolve("/" + legacy_path, urlconf=f"{legacy_app}_app.urls")
    if request.method in ("GET", "HEAD"):
        query = request.META.get("QUERY_STRING", "")
        if auth and legacy_app == "seller" and legacy_path == "register/":
            query = "role=seller" + ("&" + query if query else "")
        # A leading slash in a legacy suffix must never become a network URL.
        return HttpResponseRedirect(("/" + target.lstrip("/")) + ("?" + query if query else ""))
    if auth:
        return auth_page(request, app=legacy_app, register=legacy_path == "register/")
    return match.func(request, *match.args, **match.kwargs)
