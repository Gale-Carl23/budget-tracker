def nav_active(request):
    route = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
    groups = {
        "dashboard": "home", "transactions": "transactions", "transaction_add": "transactions", "transaction_edit": "transactions", "reports": "reports", "notifications": "notifications",
        "budgets": "budgets", "budget_add": "budgets", "calendar": "calendar", "recurring_add": "calendar",
        "accounts": "accounts", "account_add": "accounts", "goals": "goals", "goal_add": "goals", "goal_contribute": "goals",
        "debts": "debts", "debt_add": "debts", "debt_payment": "debts", "assistant": "assistant", "assistant_chat": "assistant",
        "history": "history", "undo_history": "history",
    }
    unread_notifications = 0
    if request.user.is_authenticated:
        from .models import BillNotification
        unread_notifications = BillNotification.objects.filter(user=request.user, read_at__isnull=True).count()
    return {"active": groups.get(route, ""), "unread_notifications": unread_notifications}
