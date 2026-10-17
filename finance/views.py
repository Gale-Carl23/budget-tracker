import csv
import hashlib
import hmac
import ipaddress
import json
import calendar as month_calendar
from datetime import date, timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import OuterRef, Q, Subquery, Sum
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from .forms import AccountForm, BudgetForm, DebtForm, DebtPaymentForm, GoalForm, ProfileForm, RecurringItemForm, SignupForm, TransactionForm, ContributionForm
from .models import Account, AssistantRequestLog, AuditEntry, BillNotification, Budget, Category, ChatMessage, Conversation, DebtPayment, GoalContribution, LoginThrottle, RecurringItem, SavingsGoal, Transaction, AssistantPreference
from .recurrence import add_months as _add_months, next_recurring_date as _next_recurring_date, recurring_occurrences as _recurring_occurrences

def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "finance/landing.html")

def privacy(request):
    return render(request, "finance/privacy.html")

@require_http_methods(["GET", "POST"])
def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            # Keep user creation and its starter data together. The form checks for
            # duplicates first, while this database-level guard handles two signup
            # requests arriving at nearly the same time.
            with db_transaction.atomic():
                user = get_user_model().objects.create_user(
                    username=form.cleaned_data["username"],
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password1"],
                    is_active=False,
                )
                user.profile.currency = form.cleaned_data["currency"]
                user.profile.email_verified = False
                user.profile.save(update_fields=["currency", "email_verified"])
                seed_defaults(user)
                token = signing.dumps({"user": user.pk, "email": user.email}, salt="nibi-email-verification", compress=True)
                verify_url = request.build_absolute_uri(reverse("verify_email", args=[token]))
                send_mail(
                    "Verify your email for Nibi",
                    f"Hello {user.get_username()},\n\nVerify your email address to activate your Nibi account:\n\n{verify_url}\n\nThis link expires in 24 hours. If you did not create this account, you can ignore this message.",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
        except IntegrityError:
            form.add_error("username", "That username is already in use. Try signing in or choose another.")
            return render(request, "registration/signup.html", {"form": form})
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Signup verification email failed (%s)", type(exc).__name__)
            form.add_error(None, "We could not send the verification email. Check the address and try again later.")
            return render(request, "registration/signup.html", {"form": form})
        messages.success(request, "Check your email for a verification link. It expires in 24 hours.")
        return redirect("login")
    return render(request, "registration/signup.html", {"form": form})


def verify_email(request, token):
    if request.method != "GET":
        return HttpResponseBadRequest("Invalid verification request.")
    try:
        payload = signing.loads(token, salt="nibi-email-verification", max_age=86400)
        user = get_user_model().objects.get(pk=payload["user"], email=payload["email"])
    except (signing.BadSignature, KeyError, TypeError, ValueError, get_user_model().DoesNotExist):
        messages.error(request, "That verification link is invalid or has expired. Sign up again to request a new link.")
        return redirect("signup")
    if not user.is_active:
        with db_transaction.atomic():
            user.is_active = True
            user.save(update_fields=["is_active"])
            user.profile.email_verified = True
            user.profile.save(update_fields=["email_verified"])
    messages.success(request, "Your email is verified. You can now sign in to Nibi.")
    return redirect("login")


def _login_rate_key(request, username):
    candidate = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("REMOTE_ADDR", "")
    try:
        client_ip = str(ipaddress.ip_address(candidate.strip()))
    except (ValueError, AttributeError):
        client_ip = "unknown"
    material = f"{username.strip().casefold()}|{client_ip}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), material, hashlib.sha256).hexdigest()


def _login_locked_until(key_hash, now):
    record = LoginThrottle.objects.filter(key_hash=key_hash).only("locked_until").first()
    return record.locked_until if record and record.locked_until and record.locked_until > now else None


def _record_login_failure(key_hash, now):
    window = timedelta(seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    with db_transaction.atomic():
        record, _ = LoginThrottle.objects.select_for_update().get_or_create(
            key_hash=key_hash, defaults={"window_started": now},
        )
        if record.window_started < now - window or (record.locked_until and record.locked_until <= now):
            record.window_started = now
            record.failures = 0
            record.locked_until = None
        record.failures += 1
        if record.failures >= settings.LOGIN_RATE_LIMIT_ATTEMPTS:
            record.locked_until = now + window
        record.save(update_fields=["window_started", "failures", "locked_until", "updated_at"])


def login_view(request):
    next_url = request.POST.get("next", "") if request.method == "POST" else request.GET.get("next", "")
    form = AuthenticationForm(request=request, data=request.POST or None)
    if request.method == "POST":
        username = request.POST.get("username", "")[:150]
        key_hash = _login_rate_key(request, username)
        now = timezone.now()
        if _login_locked_until(key_hash, now):
            form.add_error(None, "Too many unsuccessful sign-in attempts. Wait 15 minutes before trying again.")
        elif form.is_valid():
            user = form.get_user()
            login(request, user)
            LoginThrottle.objects.filter(key_hash=key_hash).delete()
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                next_url = reverse("dashboard")
            return redirect(next_url)
        else:
            _record_login_failure(key_hash, now)
    return render(request, "registration/login.html", {"form": form, "next": next_url})

def seed_defaults(user):
    currency = getattr(getattr(user, "profile", None), "currency", "USD")
    account_names = ["Everyday checking", "Savings"]
    existing_accounts = set(Account.objects.filter(user=user, name__in=account_names).values_list("name", flat=True))
    Account.objects.bulk_create([
        Account(user=user, name="Everyday checking", kind="checking", currency=currency),
        Account(user=user, name="Savings", kind="savings", currency=currency),
    ] if not existing_accounts else [
        Account(user=user, name=name, kind=kind, currency=currency)
        for name, kind in (("Everyday checking", "checking"), ("Savings", "savings"))
        if name not in existing_accounts
    ], ignore_conflicts=True)
    seed = [("Groceries", "expense", "🥑"), ("Dining out", "expense", "🍜"), ("Transport", "expense", "🚇"), ("Housing", "expense", "🏠"), ("Shopping", "expense", "🛍️"), ("Utilities", "expense", "💡"), ("Subscriptions", "expense", "🎧"), ("Salary", "income", "💼"), ("Side income", "income", "✨")]
    existing_categories = set(Category.objects.filter(
        user=user, name__in=[name for name, _, _ in seed],
    ).values_list("name", "kind"))
    Category.objects.bulk_create([
        Category(user=user, name=name, kind=kind, icon=icon)
        for name, kind, icon in seed if (name, kind) not in existing_categories
    ], ignore_conflicts=True)

def audit(user, action, entity, entity_id, summary, before=None, after=None, source="user", confirmed=True):
    AuditEntry.objects.create(user=user, action=action, entity=entity, entity_id=str(entity_id or ""), summary=summary, before=before or {}, after=after or {}, source=source, confirmed=confirmed)

def tx_snapshot(obj):
    return {"description": obj.description, "kind": obj.kind, "amount": str(obj.amount), "date": obj.date.isoformat(), "account": obj.account.name, "destination": obj.destination.name if obj.destination else "", "category": obj.category.name if obj.category else "", "currency": obj.currency, "payee": obj.payee, "notes": obj.notes, "tags": obj.tags}


def attach_account_balances(accounts, user):
    """Load balances for a group of accounts with two grouped queries, not per account."""
    accounts = list(accounts)
    if not accounts:
        return accounts
    account_ids = [account.pk for account in accounts]
    outgoing = {
        row["account_id"]: row
        for row in Transaction.objects.filter(user=user, account_id__in=account_ids)
        .order_by().values("account_id")
        .annotate(
            positive=Sum("amount", filter=Q(kind__in=("income", "refund"))),
            negative=Sum("amount", filter=Q(kind__in=("expense", "adjustment", "transfer"))),
        )
    }
    incoming = dict(
        Transaction.objects.filter(user=user, destination_id__in=account_ids, kind="transfer")
        .order_by().values("destination_id")
        .annotate(total=Sum("amount"))
        .values_list("destination_id", "total")
    )
    for account in accounts:
        amounts = outgoing.get(account.pk, {})
        account.balance_display = (
            account.opening_balance
            + (amounts.get("positive") or Decimal("0.00"))
            - (amounts.get("negative") or Decimal("0.00"))
            + (incoming.get(account.pk) or Decimal("0.00"))
        )
    return accounts


def attach_budget_spending(budgets, currency):
    """Annotate each budget's spend in one correlated SQL query."""
    budgets = list(budgets)
    spending = Transaction.objects.filter(
        user_id=OuterRef("user_id"), category_id=OuterRef("category_id"),
        kind="expense", currency=currency,
        date__range=(OuterRef("starts_on"), OuterRef("ends_on")),
    ).order_by().values("category_id").annotate(total=Sum("amount")).values("total")[:1]
    annotated = {
        item.pk: item
        for item in Budget.objects.filter(pk__in=[row.pk for row in budgets])
        .select_related("category").annotate(spent_total=Subquery(spending))
    }
    for budget in budgets:
        spent = annotated[budget.pk].spent_total or Decimal("0.00")
        budget.spent_display = spent
        budget.percent_display = min(100, int(spent * 100 / budget.amount)) if budget.amount else 0
        budget.remaining_display = max(Decimal("0.00"), budget.amount - spent)
    return budgets


def healthz(request):
    """Lightweight process health endpoint for the hosting platform."""
    return HttpResponse("ok", content_type="text/plain")


@login_required
def notifications(request):
    items = BillNotification.objects.filter(user=request.user).select_related("recurring_item", "recurring_item__account")
    return render(request, "finance/notifications.html", {"notifications": items[:100]})


@login_required
@require_POST
def notification_read(request, pk):
    item = get_object_or_404(BillNotification, pk=pk, user=request.user)
    if item.read_at is None:
        item.read_at = timezone.now()
        item.save(update_fields=["read_at"])
    return redirect("notifications")

@login_required
def dashboard(request):
    seed_defaults(request.user)
    today = timezone.localdate()
    currency = getattr(getattr(request.user, "profile", None), "currency", "USD")
    month_start = today.replace(day=1)
    month_end = _add_months(month_start, 1)
    month_tx = Transaction.objects.filter(user=request.user, currency=currency, date__gte=month_start, date__lt=month_end).select_related("category", "account")
    income = month_tx.filter(kind="income").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    expenses = month_tx.filter(kind="expense").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    budgets = attach_budget_spending(
        Budget.objects.filter(user=request.user, starts_on__lte=today, ends_on__gte=today).select_related("category"),
        currency,
    )
    upcoming = RecurringItem.objects.filter(user=request.user, is_active=True, next_date__gte=today).order_by("next_date")[:5]
    forecast_end = today + timedelta(days=30)
    upcoming_bills = []
    scheduled_bills = RecurringItem.objects.filter(user=request.user, is_active=True, kind="bill").select_related("account").order_by("next_date")
    for scheduled in scheduled_bills:
        # Keep an unrecorded overdue occurrence visible, then include upcoming repeats.
        if scheduled.next_date < today and (not scheduled.end_date or scheduled.next_date <= scheduled.end_date):
            upcoming_bills.append({"item": scheduled, "due_date": scheduled.next_date, "overdue": True})
        for due_date in _recurring_occurrences(scheduled, today, forecast_end):
            if due_date >= today:
                upcoming_bills.append({"item": scheduled, "due_date": due_date, "overdue": False})
    upcoming_bills.sort(key=lambda bill: (bill["due_date"], bill["item"].name.lower()))
    bill_reminders = []
    for bill in upcoming_bills:
        days_left = (bill["due_date"] - today).days
        if days_left > 7:
            continue
        if days_left < 0:
            reminder_text, level = "Overdue", "critical"
        elif days_left == 0:
            reminder_text, level = "Due today", "critical"
        elif days_left == 1:
            reminder_text, level = "1-day reminder · due tomorrow", "critical"
        elif days_left == 3:
            reminder_text, level = "3-day reminder", "warning"
        elif days_left == 7:
            reminder_text, level = "7-day heads-up", "upcoming"
        else:
            reminder_text = f"Due in {days_left} days"
            level = "warning" if days_left <= 3 else "upcoming"
        bill_reminders.append({**bill, "days_left": days_left, "reminder_text": reminder_text, "level": level})
    bill_reminders = bill_reminders[:5]
    upcoming_bills = upcoming_bills[:6]
    goals = SavingsGoal.objects.filter(user=request.user)[:3]
    user_accounts = attach_account_balances(Account.objects.filter(user=request.user, is_archived=False), request.user)
    total_balance = sum((a.balance_display for a in user_accounts if a.currency == currency), Decimal("0.00"))
    context = {"income": income, "expenses": expenses, "net": income-expenses, "total_balance": total_balance, "accounts": user_accounts, "transactions": month_tx[:7], "budgets": budgets, "upcoming": upcoming, "upcoming_bills": upcoming_bills, "bill_reminders": bill_reminders, "goals": goals, "month": today.strftime("%B %Y"), "assistant_ready": bool(__import__("os").environ.get("OPENAI_API_KEY"))}
    return render(request, "finance/dashboard.html", context)

@login_required
def transactions(request):
    qs = Transaction.objects.filter(user=request.user).select_related("category", "account", "destination")
    q = request.GET.get("q", "").strip()[:100]
    kind = request.GET.get("kind", "")
    account_id = request.GET.get("account", "")
    category_id = request.GET.get("category", "")
    start_text = request.GET.get("from", "")
    end_text = request.GET.get("to", "")
    if q: qs = qs.filter(description__icontains=q)
    if kind in {"income", "expense", "transfer", "refund", "adjustment"}: qs = qs.filter(kind=kind)
    accounts = Account.objects.filter(user=request.user).order_by("name")
    categories = Category.objects.filter(user=request.user).order_by("name", "kind")
    if account_id.isdigit():
        qs = qs.filter(account_id=account_id, account__user=request.user)
    else:
        account_id = ""
    if category_id.isdigit():
        qs = qs.filter(category_id=category_id, category__user=request.user)
    else:
        category_id = ""
    try:
        start_date = date.fromisoformat(start_text) if start_text else None
        end_date = date.fromisoformat(end_text) if end_text else None
        if start_date and end_date and end_date < start_date:
            raise ValueError
    except ValueError:
        start_date = end_date = None
        start_text = end_text = ""
        messages.error(request, "Choose a valid transaction date range.")
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    page_obj = Paginator(qs, 50).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "finance/transactions.html", {
        "transactions": page_obj.object_list, "page_obj": page_obj, "q": q, "kind": kind,
        "accounts": accounts, "categories": categories, "account_filter": account_id,
        "category_filter": category_id, "start_filter": start_text, "end_filter": end_text,
        "filter_query": params.urlencode(),
    })

@login_required
def reports(request):
    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET.get("from", "")) if request.GET.get("from") else today.replace(day=1)
        end = date.fromisoformat(request.GET.get("to", "")) if request.GET.get("to") else today
        if end < start: raise ValueError
    except ValueError:
        start, end = today.replace(day=1), today
        messages.error(request, "Choose a valid report date range.")
    currency = getattr(getattr(request.user, "profile", None), "currency", "USD")
    qs = Transaction.objects.filter(user=request.user, currency=currency, date__range=(start, end)).select_related("category", "account")
    income = qs.filter(kind="income").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    expense = qs.filter(kind="expense").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    by_category = list(qs.filter(kind="expense").values("category__name", "category__icon").annotate(total=Sum("amount")).order_by("-total"))
    total_expense = sum((row["total"] or Decimal("0") for row in by_category), Decimal("0"))
    for row in by_category:
        row["percent"] = int(row["total"] * 100 / total_expense) if total_expense else 0
    return render(request, "finance/reports.html", {"start": start, "end": end, "income": income, "expense": expense, "net": income-expense, "by_category": by_category, "transactions": qs[:100]})

@login_required
def transaction_add(request):
    seed_defaults(request.user)
    form = TransactionForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False); item.user = request.user; item.currency = item.account.currency
        bill_risk = _bill_shortfall_warning(request.user, item.account, item.amount) if item.kind == "expense" else None
        if bill_risk and not _bill_risk_confirmation_matches(request, item.account, item.amount):
            confirmation = signing.dumps({"user": request.user.pk, "account": item.account.pk, "amount": str(item.amount)}, salt="bill-risk-confirmation")
            return render(request, "finance/form.html", {"form": form, "title": "Add transaction", "cancel_url": "transactions", "bill_risk": bill_risk, "bill_risk_confirmation": confirmation})
        item.full_clean(); item.save()
        audit(request.user, "create", "transaction", item.pk, f"Added {item.kind}: {item.description} · {item.currency} {item.amount}", after=tx_snapshot(item))
        messages.success(request, "Transaction added.")
        return redirect("transactions")
    return render(request, "finance/form.html", {"form": form, "title": "Add transaction", "cancel_url": "transactions"})

@login_required
def transaction_edit(request, pk):
    item = get_object_or_404(Transaction, pk=pk, user=request.user)
    before = tx_snapshot(item)
    form = TransactionForm(request.POST or None, instance=item, user=request.user)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False); updated.full_clean(); updated.save()
        audit(request.user, "update", "transaction", item.pk, f"Updated transaction: {updated.description}", before=before, after=tx_snapshot(updated))
        messages.success(request, "Transaction updated.")
        return redirect("transactions")
    return render(request, "finance/form.html", {"form": form, "title": "Edit transaction", "cancel_url": "transactions"})

@login_required
@require_POST
def transaction_delete(request, pk):
    item = get_object_or_404(Transaction, pk=pk, user=request.user)
    before = tx_snapshot(item)
    audit(request.user, "delete", "transaction", item.pk, f"Deleted transaction: {item.description}", before=before)
    item.delete()
    messages.success(request, "Transaction deleted. The change is recorded in your history.")
    return redirect("transactions")

@login_required
def accounts(request):
    accounts = attach_account_balances(Account.objects.filter(user=request.user).order_by("is_archived", "name"), request.user)
    return render(request, "finance/accounts.html", {"accounts": accounts})

@login_required
def account_add(request):
    form = AccountForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.user = request.user; obj.save()
        audit(request.user, "create", "account", obj.pk, f"Added account: {obj.name}", after={"name": obj.name, "type": obj.kind})
        messages.success(request, "Account created.")
        return redirect("accounts")
    return render(request, "finance/form.html", {"form": form, "title": "Add account", "cancel_url": "accounts"})

@login_required
@require_POST
def account_remove(request, pk):
    account = get_object_or_404(Account, pk=pk, user=request.user)
    has_transactions = Transaction.objects.filter(user=request.user).filter(Q(account=account) | Q(destination=account)).exists()
    has_scheduled_items = RecurringItem.objects.filter(user=request.user, account=account).exists()
    has_debt_payments = DebtPayment.objects.filter(account=account, debt__user=request.user).exists()
    has_goals = SavingsGoal.objects.filter(user=request.user, account=account).exists()
    if has_transactions or has_scheduled_items or has_debt_payments or has_goals:
        messages.error(request, "This account is linked to financial records or savings goals and can’t be deleted. Archive it to keep its history safely.")
        return redirect("accounts")
    snapshot = {"name": account.name, "kind": account.kind, "opening_balance": str(account.opening_balance), "currency": account.currency}
    audit(request.user, "delete", "account", account.pk, f"Deleted account: {account.name}", before=snapshot)
    account.delete()
    messages.success(request, f"{account.name} deleted. The change is recorded in your history.")
    return redirect("accounts")

@login_required
@require_POST
def account_archive(request, pk):
    account = get_object_or_404(Account, pk=pk, user=request.user)
    was_archived = account.is_archived
    account.is_archived = not was_archived
    account.save(update_fields=["is_archived"])
    action = "Restored" if was_archived else "Archived"
    audit(request.user, "update", "account", account.pk, f"{action} account: {account.name}", before={"is_archived": was_archived}, after={"is_archived": account.is_archived})
    messages.success(request, f"{account.name} {action.lower()}. Its financial history is preserved.")
    return redirect("accounts")

@login_required
def budgets(request):
    currency = getattr(getattr(request.user, "profile", None), "currency", "USD")
    budgets = attach_budget_spending(Budget.objects.filter(user=request.user).select_related("category"), currency)
    return render(request, "finance/budgets.html", {"budgets": budgets})

@login_required
def budget_add(request):
    form = BudgetForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.user = request.user; obj.save()
        audit(request.user, "create", "budget", obj.pk, f"Created budget for {obj.category.name}", after={"amount": str(obj.amount), "category": obj.category.name})
        messages.success(request, "Budget created.")
        return redirect("budgets")
    return render(request, "finance/form.html", {"form": form, "title": "Create budget", "cancel_url": "budgets"})

@login_required
def budget_edit(request, pk):
    item = get_object_or_404(Budget.objects.select_related("category"), pk=pk, user=request.user)
    before = {"category": item.category.name, "amount": str(item.amount), "starts_on": item.starts_on.isoformat(), "ends_on": item.ends_on.isoformat(), "rollover": item.rollover}
    form = BudgetForm(request.POST or None, instance=item, user=request.user)
    if request.method == "POST" and form.is_valid():
        updated = form.save()
        after = {"category": updated.category.name, "amount": str(updated.amount), "starts_on": updated.starts_on.isoformat(), "ends_on": updated.ends_on.isoformat(), "rollover": updated.rollover}
        audit(request.user, "update", "budget", updated.pk, f"Updated budget for {updated.category.name}", before=before, after=after)
        messages.success(request, "Budget updated.")
        return redirect("budgets")
    return render(request, "finance/form.html", {"form": form, "title": "Edit budget", "cancel_url": "budgets"})

@login_required
@require_POST
def budget_delete(request, pk):
    item = get_object_or_404(Budget.objects.select_related("category"), pk=pk, user=request.user)
    snapshot = {"category": item.category.name, "amount": str(item.amount), "starts_on": item.starts_on.isoformat(), "ends_on": item.ends_on.isoformat(), "rollover": item.rollover}
    audit(request.user, "delete", "budget", item.pk, f"Deleted budget for {item.category.name}", before=snapshot)
    item.delete()
    messages.success(request, "Budget deleted. The change is recorded in your history.")
    return redirect("budgets")

@login_required
def goals(request):
    return render(request, "finance/goals.html", {"goals": SavingsGoal.objects.filter(user=request.user).prefetch_related("contributions")})

@login_required
def goal_add(request):
    form = GoalForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.user = request.user; obj.save()
        audit(request.user, "create", "goal", obj.pk, f"Created savings goal: {obj.name}", after={"target": str(obj.target_amount)})
        messages.success(request, "Savings goal created.")
        return redirect("goals")
    return render(request, "finance/form.html", {"form": form, "title": "Create savings goal", "cancel_url": "goals"})

@login_required
@require_POST
def goal_contribute(request, pk):
    goal = get_object_or_404(SavingsGoal, pk=pk, user=request.user)
    form = ContributionForm(request.POST)
    if form.is_valid():
        contribution = form.save(commit=False); contribution.goal = goal; contribution.save()
        audit(request.user, "create", "goal contribution", contribution.pk, f"Added {contribution.amount} to {goal.name}")
        messages.success(request, "Goal contribution recorded.")
    else:
        messages.error(request, "Enter a valid contribution amount and date.")
    return redirect("goals")

def _bill_shortfall_warning(user, account, planned_spend, as_of=None):
    """Return a warning when a proposed purchase would leave a scheduled bill short."""
    as_of = as_of or timezone.localdate()
    forecast_end = as_of + timedelta(days=30)
    scheduled = RecurringItem.objects.filter(
        user=user, account=account, is_active=True,
        next_date__lte=forecast_end,
    ).select_related("account")
    events = []
    for item in scheduled:
        if item.kind == "bill" and item.next_date < as_of:
            events.append((item.next_date, 1, item))
        for due_date in _recurring_occurrences(item, as_of, forecast_end):
            events.append((due_date, 0 if item.kind == "income" else 1, item))
    events.sort(key=lambda event: (event[0], event[1]))
    if not any(item.kind == "bill" for _, _, item in events):
        return None

    balance = account.current_balance - planned_spend
    for due_date, _, item in events:
        if item.kind == "income":
            balance += item.amount
            continue
        balance -= item.amount
        if balance < 0:
            return {
                "bill_name": item.name,
                "due_date": due_date,
                "shortfall": -balance,
                "account_name": account.name,
                "currency": account.currency,
            }
    return None

def _bill_risk_confirmation_matches(request, account, amount):
    try:
        confirmation = signing.loads(request.POST.get("bill_risk_confirmation", ""), salt="bill-risk-confirmation", max_age=900)
    except signing.BadSignature:
        return False
    return confirmation == {"user": request.user.pk, "account": account.pk, "amount": str(amount)}

@login_required
def calendar(request):
    today = timezone.localdate()
    try:
        year_text, month_text = request.GET.get("month", "").split("-", 1)
        year, month_number = int(year_text), int(month_text)
        if not today.year - 20 <= year <= today.year + 20 or not 1 <= month_number <= 12:
            raise ValueError
    except (ValueError, TypeError):
        year, month_number = today.year, today.month
    month_start = date(year, month_number, 1)
    month_end = date(year, month_number, month_calendar.monthrange(year, month_number)[1])
    month = month_start.strftime("%B %Y")
    items = list(RecurringItem.objects.filter(user=request.user).select_related("account", "category").order_by("-is_active", "next_date", "name"))
    transactions = list(Transaction.objects.filter(user=request.user, date__range=(month_start, month_end)).select_related("category", "account"))

    events_by_date = {}
    for transaction in transactions:
        events_by_date.setdefault(transaction.date, []).append({
            "type": "transaction", "kind": transaction.kind, "label": transaction.description,
            "amount": transaction.amount, "currency": transaction.currency,
        })
    for item in items:
        if not item.is_active:
            continue
        for occurrence in _recurring_occurrences(item, month_start, month_end):
            events_by_date.setdefault(occurrence, []).append({
                "type": "scheduled", "kind": "bill" if item.kind == "bill" else "income",
                "label": item.name, "amount": item.amount, "currency": item.account.currency,
            })

    weeks = []
    for week in month_calendar.Calendar(firstweekday=6).monthdatescalendar(year, month_number):
        weeks.append([{
            "date": day, "in_month": day.month == month_number,
            "events": events_by_date.get(day, []) if day.month == month_number else [],
        } for day in week])

    item_rows = []
    for item in items:
        if not item.is_active:
            status = "Paused"
            status_class = "paused"
        elif item.next_date < today:
            status = "Overdue"
            status_class = "overdue"
        elif item.next_date == today:
            status = "Due today"
            status_class = "due-today"
        elif (item.next_date - today).days == 1:
            status = "Due tomorrow · 1 day"
            status_class = "due-tomorrow"
        elif (item.next_date - today).days <= 3:
            status = f"Due in {(item.next_date - today).days} days · 3-day reminder"
            status_class = "due-3"
        elif (item.next_date - today).days <= 7:
            status = f"Due in {(item.next_date - today).days} days · 7-day heads-up"
            status_class = "due-7"
        else:
            status = "Upcoming"
            status_class = "upcoming"
        item_rows.append({"item": item, "status": status, "status_class": status_class})

    return render(request, "finance/calendar.html", {
        "items": item_rows, "transactions": transactions, "month": month, "weeks": weeks,
        "month_key": month_start.strftime("%Y-%m"), "previous_month": _add_months(month_start, -1).strftime("%Y-%m"),
        "next_month": _add_months(month_start, 1).strftime("%Y-%m"),
        "today": today, "currency": request.user.profile.currency,
    })

@login_required
def recurring_add(request):
    form = RecurringItemForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False); item.user = request.user; item.save()
        audit(request.user, "create", "recurring item", item.pk, f"Scheduled {item.kind}: {item.name}", after={"amount": str(item.amount), "next_date": item.next_date.isoformat(), "frequency": item.frequency})
        messages.success(request, "Scheduled item created. It remains a forecast until you record it as paid or received.")
        return redirect("calendar")
    return render(request, "finance/form.html", {"form": form, "title": "Add planned payment or income", "cancel_url": "calendar"})

@login_required
def recurring_edit(request, pk):
    item = get_object_or_404(RecurringItem, pk=pk, user=request.user)
    before = {"name": item.name, "kind": item.kind, "amount": str(item.amount), "account": item.account.name, "category": item.category.name if item.category else "", "next_date": item.next_date.isoformat(), "frequency": item.frequency, "end_date": item.end_date.isoformat() if item.end_date else ""}
    form = RecurringItemForm(request.POST or None, instance=item, user=request.user)
    if request.method == "POST" and form.is_valid():
        updated = form.save()
        after = {"name": updated.name, "kind": updated.kind, "amount": str(updated.amount), "account": updated.account.name, "category": updated.category.name if updated.category else "", "next_date": updated.next_date.isoformat(), "frequency": updated.frequency, "end_date": updated.end_date.isoformat() if updated.end_date else ""}
        audit(request.user, "update", "recurring item", updated.pk, f"Updated scheduled item: {updated.name}", before=before, after=after)
        messages.success(request, "Scheduled item updated.")
        return redirect("calendar")
    return render(request, "finance/form.html", {"form": form, "title": "Edit planned item", "cancel_url": "calendar"})

@login_required
@require_POST
def recurring_toggle(request, pk):
    item = get_object_or_404(RecurringItem, pk=pk, user=request.user)
    was_active = item.is_active
    item.is_active = not item.is_active
    item.save(update_fields=["is_active"])
    audit(request.user, "update", "recurring item", item.pk, f"{'Resumed' if item.is_active else 'Paused'} scheduled item: {item.name}", before={"is_active": was_active}, after={"is_active": item.is_active})
    messages.success(request, f"{item.name} {'resumed' if item.is_active else 'paused'}.")
    return redirect("calendar")

@login_required
@require_POST
def recurring_record(request, pk):
    today = timezone.localdate()
    try:
        amount = Decimal(request.POST.get("amount", ""))
        paid_date = date.fromisoformat(request.POST.get("date", ""))
        scheduled_date = date.fromisoformat(request.POST.get("scheduled_date", ""))
        if not amount.is_finite() or amount <= 0 or amount > Decimal("999999999999.99") or paid_date > today:
            raise ValueError
    except (ValueError, TypeError, ArithmeticError):
        messages.error(request, "Enter a valid positive amount and a payment date that is not in the future.")
        return redirect("calendar")

    with db_transaction.atomic():
        item = get_object_or_404(RecurringItem.objects.select_for_update().select_related("account", "category"), pk=pk, user=request.user)
        if not item.is_active or scheduled_date != item.next_date:
            messages.error(request, "This scheduled item has changed. Refresh the calendar and try again.")
            return redirect("calendar")
        kind = "expense" if item.kind == "bill" else "income"
        category = item.category
        if not category or category.kind != kind:
            category_name = "Bills" if kind == "expense" else "Other income"
            category, _ = Category.objects.get_or_create(user=request.user, name=category_name, kind=kind, defaults={"icon": "🧾" if kind == "expense" else "↙"})
        entry = Transaction(user=request.user, account=item.account, category=category, kind=kind, amount=amount, currency=item.account.currency, description=item.name, date=paid_date)
        entry.full_clean()
        entry.save()
        audit(request.user, "create", "transaction", entry.pk, f"Recorded {item.kind}: {entry.description} · {entry.currency} {entry.amount}", after=tx_snapshot(entry))
        before_next = item.next_date
        next_date = _next_recurring_date(item.next_date, item.frequency)
        item.next_date = next_date
        if item.end_date and next_date > item.end_date:
            item.is_active = False
        item.save(update_fields=["next_date", "is_active"])
        audit(request.user, "update", "recurring item", item.pk, f"Recorded {item.kind}: {item.name}", before={"next_date": before_next.isoformat()}, after={"next_date": item.next_date.isoformat(), "is_active": item.is_active})
    messages.success(request, f"{item.name} recorded in your transactions. The next date is {item.next_date.strftime('%b')} {item.next_date.day}, {item.next_date.year}.")
    return redirect("calendar")

@login_required
def debts(request):
    return render(request, "finance/debts.html", {"debts": request.user.debts.prefetch_related("payments"), "accounts": Account.objects.filter(user=request.user, is_archived=False)})

@login_required
def debt_add(request):
    form = DebtForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False); item.user = request.user; item.save()
        audit(request.user, "create", "debt", item.pk, f"Added {item.get_kind_display().lower()}: {item.name}", after={"amount": str(item.original_amount)})
        messages.success(request, "Debt or receivable added.")
        return redirect("debts")
    return render(request, "finance/form.html", {"form": form, "title": "Add debt or money owed", "cancel_url": "debts"})

@login_required
@require_POST
def debt_payment(request, pk):
    debt = get_object_or_404(request.user.debts, pk=pk)
    form = DebtPaymentForm(request.POST, user=request.user)
    if not form.is_valid():
        messages.error(request, "Enter a valid payment amount, account, and date.")
        return redirect("debts")
    payment = form.save(commit=False); payment.debt = debt
    if payment.amount > debt.remaining:
        messages.error(request, "That payment is greater than the remaining balance.")
        return redirect("debts")
    with db_transaction.atomic():
        payment.save()
        kind = "expense" if debt.kind == "owed" else "income"
        category_name = "Debt repayment" if kind == "expense" else "Debt collection"
        category, _ = Category.objects.get_or_create(user=request.user, name=category_name, kind=kind, defaults={"icon": "↔"})
        entry = Transaction.objects.create(user=request.user, account=payment.account, category=category, kind=kind, amount=payment.amount, currency=payment.account.currency, description=f"{category_name}: {debt.name}", date=payment.date, notes=payment.notes)
        payment.transaction = entry; payment.save(update_fields=["transaction"])
        audit(request.user, "create", "debt payment", payment.pk, f"Recorded {kind}: {payment.amount} for {debt.name}", after={"remaining": str(debt.remaining)}, source="user")
        audit(request.user, "create", "transaction", entry.pk, f"{category_name}: {debt.name} · {entry.currency} {entry.amount}", after=tx_snapshot(entry))
    messages.success(request, "Payment recorded and reflected in your ledger.")
    return redirect("debts")

@login_required
def history(request):
    return render(request, "finance/history.html", {"entries": AuditEntry.objects.filter(user=request.user)[:200]})

@login_required
@require_POST
def undo_history(request, pk):
    entry = get_object_or_404(AuditEntry, pk=pk, user=request.user)
    if entry.undone or entry.entity != "transaction" or entry.action not in {"create", "confirm_ai", "update", "delete"}:
        messages.error(request, "This change cannot be undone from here.")
        return redirect("history")
    with db_transaction.atomic():
        if entry.action in {"create", "confirm_ai"}:
            item = get_object_or_404(Transaction, pk=entry.entity_id, user=request.user)
            prior = tx_snapshot(item); item.delete()
            detail = f"Removed transaction: {prior['description']}"
        else:
            target = entry.before if entry.action in {"update", "delete"} else {}
            item = Transaction.objects.filter(pk=entry.entity_id, user=request.user).first()
            if entry.action == "delete":
                if item:
                    messages.error(request, "A replacement transaction already exists; this deletion cannot be restored safely.")
                    return redirect("history")
                account = get_object_or_404(Account, user=request.user, name=target.get("account"))
                item = Transaction(user=request.user, account=account, amount=Decimal(target["amount"]), kind=target["kind"], description=target["description"], date=date.fromisoformat(target["date"]), currency=target.get("currency") or request.user.profile.currency, payee=target.get("payee", ""), notes=target.get("notes", ""), tags=target.get("tags", ""))
                if target.get("destination"):
                    item.destination = get_object_or_404(Account, user=request.user, name=target["destination"])
                if target.get("category"):
                    item.category = Category.objects.filter(user=request.user, name=target["category"], kind=target["kind"]).first()
                item.full_clean(); item.save()
                detail = f"Restored transaction: {item.description}"
            else:
                if not item:
                    messages.error(request, "The transaction no longer exists; this edit cannot be undone safely.")
                    return redirect("history")
                item.description = target["description"]; item.kind = target["kind"]; item.amount = Decimal(target["amount"]); item.date = date.fromisoformat(target["date"])
                item.account = get_object_or_404(Account, user=request.user, name=target["account"])
                item.destination = get_object_or_404(Account, user=request.user, name=target["destination"]) if target.get("destination") else None
                item.category = Category.objects.filter(user=request.user, name=target.get("category"), kind=target["kind"]).first() if target.get("category") else None
                item.currency = target.get("currency", item.currency); item.payee = target.get("payee", ""); item.notes = target.get("notes", ""); item.tags = target.get("tags", "")
                item.full_clean(); item.save(); detail = f"Restored previous version of: {item.description}"
        entry.undone = True; entry.save(update_fields=["undone"])
        audit(request.user, "undo", "transaction", entry.entity_id, detail, source="user")
    messages.success(request, "Change undone. A record of the undo was added to history.")
    return redirect("history")

@login_required
def assistant(request):
    conversation = Conversation.objects.filter(user=request.user).order_by("-updated_at").first()
    if not conversation:
        conversation = Conversation.objects.create(user=request.user)
    return render(request, "finance/assistant.html", {
        "conversation": conversation,
        "chat_messages": conversation.messages.order_by("created_at"),
        "configured": bool(__import__("os").environ.get("OPENAI_API_KEY")),
        "ai_requests_per_minute": settings.AI_REQUESTS_PER_MINUTE,
        "ai_requests_per_day": settings.AI_REQUESTS_PER_DAY,
    })

def _json_body(request):
    if len(request.body) > 20_000:
        raise ValueError("Request is too large.")
    return json.loads(request.body or b"{}")

def _reserve_assistant_request(user):
    now = timezone.now()
    with db_transaction.atomic():
        # Serialize quota checks per user on databases that support row locks.
        get_user_model().objects.select_for_update().only("pk").get(pk=user.pk)
        logs = AssistantRequestLog.objects.filter(user=user)
        logs.filter(created_at__lt=now - timedelta(days=1)).delete()
        if logs.filter(created_at__gte=now - timedelta(days=1)).count() >= settings.AI_REQUESTS_PER_DAY:
            return 86400
        if logs.filter(created_at__gte=now - timedelta(minutes=1)).count() >= settings.AI_REQUESTS_PER_MINUTE:
            return 60
        AssistantRequestLog.objects.create(user=user)
    return None

@login_required
@require_POST
def assistant_chat(request):
    try:
        data = _json_body(request)
        text = str(data.get("message", "")).strip()
        if not text or len(text) > 4000:
            return JsonResponse({"error": "Enter a message under 4,000 characters."}, status=400)
        retry_after = _reserve_assistant_request(request.user)
        if retry_after:
            response = JsonResponse({"error": "You’ve reached the assistant usage limit. Please try again later."}, status=429)
            response["Retry-After"] = str(retry_after)
            return response
        conversation_id = data.get("conversation_id")
        if conversation_id:
            conversation = get_object_or_404(Conversation, pk=conversation_id, user=request.user)
        else:
            conversation = Conversation.objects.create(user=request.user)
        history_data = list(conversation.messages.order_by("-created_at").values("role", "content")[:10])[::-1]
        ChatMessage.objects.create(conversation=conversation, role="user", content=text)
        from finance.services.assistant import ask_assistant
        result = ask_assistant(request.user, history_data, text)
        proposals = result.get("transactions", [])
        assistant_message = ChatMessage.objects.create(conversation=conversation, role="assistant", content=result.get("reply", ""), metadata={"proposals": proposals})
        draft = signing.dumps({"uid": request.user.pk, "conversation": conversation.pk, "message": assistant_message.pk, "transactions": proposals}, salt="ai-transaction-draft") if proposals else ""
        conversation.save(update_fields=["updated_at"])
        return JsonResponse({"reply": result.get("reply", ""), "transactions": proposals, "draft_token": draft, "conversation_id": conversation.pk})
    except RuntimeError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=422)
    except Exception as exc:
        # Do not put chat content, ledger context, or provider error bodies in logs.
        import logging
        logging.getLogger(__name__).error("Assistant request failed (%s)", type(exc).__name__)
        return JsonResponse({"error": "The assistant could not complete that request. Check the server configuration and try again."}, status=502)

@login_required
@require_POST
def assistant_confirm(request):
    try:
        data = _json_body(request)
        payload = signing.loads(str(data.get("draft_token", "")), salt="ai-transaction-draft", max_age=900)
        if payload.get("uid") != request.user.pk:
            return JsonResponse({"error": "This proposal belongs to another session."}, status=403)
        conversation = get_object_or_404(Conversation, pk=payload["conversation"], user=request.user)
        proposed_message = get_object_or_404(ChatMessage.objects.select_for_update(), pk=payload["message"], conversation=conversation, role="assistant")
        if proposed_message.metadata.get("confirmed"):
            return JsonResponse({"error": "This proposal has already been saved."}, status=409)
        entries = data.get("transactions", payload.get("transactions", []))
        if not entries or len(entries) > 20:
            return JsonResponse({"error": "There are no valid transactions to save."}, status=400)
        if not data.get("confirm_bill_risk"):
            proposed_spend = {}
            for entry in entries:
                if entry.get("kind") != "expense":
                    continue
                account = get_object_or_404(Account, user=request.user, name=entry.get("account"), is_archived=False)
                try:
                    amount = Decimal(str(entry.get("amount", "")))
                except (ValueError, TypeError, ArithmeticError):
                    continue
                if amount.is_finite() and amount > 0:
                    proposed_spend[account.pk] = (account, proposed_spend.get(account.pk, (account, Decimal("0.00")))[1] + amount)
            for account, amount in proposed_spend.values():
                bill_risk = _bill_shortfall_warning(request.user, account, amount)
                if bill_risk:
                    due_date = bill_risk["due_date"]
                    warning = (
                        f"These expenses may leave {bill_risk['shortfall']:.2f} {bill_risk['currency']} "
                        f"short in {bill_risk['account_name']} for {bill_risk['bill_name']} due "
                        f"{due_date.strftime('%b')} {due_date.day}. You can still choose to save them."
                    )
                    return JsonResponse({"requires_confirmation": True, "warning": warning})
        saved = []
        with db_transaction.atomic():
            for entry in entries:
                account = get_object_or_404(Account, user=request.user, name=entry.get("account"), is_archived=False)
                category = Category.objects.filter(user=request.user, name__iexact=entry.get("category"), kind=entry.get("kind")).first()
                if not category:
                    category = Category.objects.create(user=request.user, name=entry.get("category") or "Other", kind=entry["kind"], icon=entry.get("icon", "•"))
                item = Transaction(user=request.user, account=account, category=category, kind=entry["kind"], amount=Decimal(str(entry["amount"])), currency=account.currency, description=str(entry.get("description", category.name))[:160], date=date.fromisoformat(entry["date"]), source="assistant")
                item.full_clean(); item.save(); saved.append(item)
                audit(request.user, "confirm_ai", "transaction", item.pk, f"Confirmed AI proposal: {item.description} · {item.currency} {item.amount}", after=tx_snapshot(item), source="assistant")
                if data.get("remember"):
                    _, created = AssistantPreference.objects.get_or_create(user=request.user, trigger=item.description[:120], defaults={"category": category, "account": account, "note": "Saved from a confirmed assistant entry"})
                    if created:
                        audit(request.user, "preference", "assistant preference", item.description[:120], f"Remembered choices for {item.description}", after={"category": category.name, "account": account.name}, source="assistant")
            proposed_message.metadata = {**proposed_message.metadata, "confirmed": True, "saved_ids": [x.pk for x in saved]}
            proposed_message.save(update_fields=["metadata"])
            ChatMessage.objects.create(conversation=conversation, role="assistant", content=f"Saved {len(saved)} transaction(s) after your confirmation.", metadata={"saved_ids": [x.pk for x in saved]})
        return JsonResponse({"ok": True, "saved": len(saved), "message": "Saved to your ledger."})
    except signing.BadSignature:
        return JsonResponse({"error": "This proposal expired. Please ask the assistant again."}, status=400)
    except (ValueError, TypeError, KeyError) as exc:
        return JsonResponse({"error": "The proposal contains invalid details. Please try again."}, status=422)

@login_required
def preferences(request):
    prefs = AssistantPreference.objects.filter(user=request.user).select_related("category", "account")
    chat_message_count = ChatMessage.objects.filter(conversation__user=request.user).count()
    return render(request, "finance/preferences.html", {"preferences": prefs, "chat_message_count": chat_message_count})

@login_required
@require_POST
def assistant_history_clear(request):
    Conversation.objects.filter(user=request.user).delete()
    messages.success(request, "Your assistant chat history was deleted. Content-free usage-limit records expire after 24 hours.")
    return redirect("preferences")

@login_required
def profile_settings(request):
    profile = request.user.profile
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        before = {"currency": profile.currency, "locale": profile.locale}
        form.save()
        audit(request.user, "update", "profile", profile.pk, "Updated currency or locale preferences", before=before, after={"currency": profile.currency, "locale": profile.locale})
        messages.success(request, "Your currency and locale preferences were updated. Existing transactions keep their original currencies.")
        return redirect("profile_settings")
    return render(request, "finance/settings.html", {"form": form})

@login_required
@require_POST
def account_delete(request):
    if request.POST.get("confirmation", "") != "DELETE" or not request.user.check_password(request.POST.get("password", "")):
        messages.error(request, "Account deletion was not confirmed. Enter your current password and type DELETE exactly.")
        return redirect("profile_settings")
    user = request.user
    with db_transaction.atomic():
        # Remove rows that protect accounts before the user cascade removes accounts.
        Transaction.objects.filter(user=user).delete()
        RecurringItem.objects.filter(user=user).delete()
        DebtPayment.objects.filter(debt__user=user).delete()
        user.delete()
    logout(request)
    messages.success(request, "Your Nibi account and associated data were deleted.")
    return redirect("landing")

@login_required
@require_POST
def preference_delete(request, pk):
    pref = get_object_or_404(AssistantPreference, pk=pk, user=request.user)
    audit(request.user, "delete", "assistant preference", pref.pk, f"Removed assistant preference: {pref.trigger}")
    pref.delete()
    messages.success(request, "Preference removed.")
    return redirect("preferences")

@login_required
def export_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="nibi-transactions.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Date", "Type", "Amount", "Currency", "Category", "Account", "Description", "Payee", "Notes", "Tags"])
    for item in Transaction.objects.filter(user=request.user).select_related("category", "account"):
        writer.writerow([item.date, item.kind, item.amount, item.currency, item.category.name if item.category else "", item.account.name, item.description, item.payee, item.notes, item.tags])
    return response
