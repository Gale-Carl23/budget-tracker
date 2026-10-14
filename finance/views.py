import csv
import json
from datetime import date, timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Sum
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import AccountForm, BudgetForm, DebtForm, DebtPaymentForm, GoalForm, ProfileForm, RecurringItemForm, SignupForm, TransactionForm, ContributionForm
from .models import Account, AssistantRequestLog, AuditEntry, Budget, Category, ChatMessage, Conversation, DebtPayment, GoalContribution, RecurringItem, SavingsGoal, Transaction, AssistantPreference

def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "finance/landing.html")

def privacy(request):
    return render(request, "finance/privacy.html")

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
                )
                user.profile.currency = form.cleaned_data["currency"]
                user.profile.save(update_fields=["currency"])
                seed_defaults(user)
        except IntegrityError:
            form.add_error("username", "That username is already in use. Try signing in or choose another.")
            return render(request, "registration/signup.html", {"form": form})
        login(request, user)
        messages.success(request, "Welcome! Your personal money space is ready.")
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})

def seed_defaults(user):
    Account.objects.get_or_create(user=user, name="Everyday checking", defaults={"kind": "checking", "currency": getattr(getattr(user, "profile", None), "currency", "USD")})
    Account.objects.get_or_create(user=user, name="Savings", defaults={"kind": "savings", "currency": getattr(getattr(user, "profile", None), "currency", "USD")})
    seed = [("Groceries", "expense", "🥑"), ("Dining out", "expense", "🍜"), ("Transport", "expense", "🚇"), ("Housing", "expense", "🏠"), ("Shopping", "expense", "🛍️"), ("Utilities", "expense", "💡"), ("Subscriptions", "expense", "🎧"), ("Salary", "income", "💼"), ("Side income", "income", "✨")]
    for name, kind, icon in seed:
        Category.objects.get_or_create(user=user, name=name, kind=kind, defaults={"icon": icon})

def audit(user, action, entity, entity_id, summary, before=None, after=None, source="user", confirmed=True):
    AuditEntry.objects.create(user=user, action=action, entity=entity, entity_id=str(entity_id or ""), summary=summary, before=before or {}, after=after or {}, source=source, confirmed=confirmed)

def tx_snapshot(obj):
    return {"description": obj.description, "kind": obj.kind, "amount": str(obj.amount), "date": obj.date.isoformat(), "account": obj.account.name, "destination": obj.destination.name if obj.destination else "", "category": obj.category.name if obj.category else "", "currency": obj.currency, "payee": obj.payee, "notes": obj.notes, "tags": obj.tags}

@login_required
def dashboard(request):
    seed_defaults(request.user)
    today = timezone.localdate()
    currency = getattr(getattr(request.user, "profile", None), "currency", "USD")
    month_tx = Transaction.objects.filter(user=request.user, currency=currency, date__year=today.year, date__month=today.month).select_related("category", "account")
    income = month_tx.filter(kind="income").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    expenses = month_tx.filter(kind="expense").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    budgets = Budget.objects.filter(user=request.user, starts_on__lte=today, ends_on__gte=today).select_related("category")
    upcoming = RecurringItem.objects.filter(user=request.user, is_active=True, next_date__gte=today).order_by("next_date")[:5]
    goals = SavingsGoal.objects.filter(user=request.user)[:3]
    user_accounts = list(Account.objects.filter(user=request.user, is_archived=False))
    total_balance = sum((a.current_balance for a in user_accounts if a.currency == currency), Decimal("0.00"))
    context = {"income": income, "expenses": expenses, "net": income-expenses, "total_balance": total_balance, "accounts": user_accounts, "transactions": month_tx[:7], "budgets": budgets, "upcoming": upcoming, "goals": goals, "month": today.strftime("%B %Y"), "assistant_ready": bool(__import__("os").environ.get("OPENAI_API_KEY"))}
    return render(request, "finance/dashboard.html", context)

@login_required
def transactions(request):
    qs = Transaction.objects.filter(user=request.user).select_related("category", "account", "destination")
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "")
    if q: qs = qs.filter(description__icontains=q)
    if kind in {"income", "expense", "transfer", "refund", "adjustment"}: qs = qs.filter(kind=kind)
    return render(request, "finance/transactions.html", {"transactions": qs[:250], "q": q, "kind": kind})

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
        item = form.save(commit=False); item.user = request.user; item.currency = item.account.currency; item.full_clean(); item.save()
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
    return render(request, "finance/accounts.html", {"accounts": Account.objects.filter(user=request.user)})

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
def budgets(request):
    return render(request, "finance/budgets.html", {"budgets": Budget.objects.filter(user=request.user).select_related("category")})

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

@login_required
def calendar(request):
    today = timezone.localdate()
    items = RecurringItem.objects.filter(user=request.user, is_active=True).select_related("account", "category").order_by("next_date")
    transactions_for_month = Transaction.objects.filter(user=request.user, date__year=today.year, date__month=today.month).select_related("category")
    return render(request, "finance/calendar.html", {"items": items, "transactions": transactions_for_month, "month": today.strftime("%B %Y")})

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
