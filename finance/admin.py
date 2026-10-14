from django.contrib import admin
from .models import Account, AssistantPreference, AuditEntry, Budget, Category, ChatMessage, Conversation, Debt, DebtPayment, GoalContribution, Profile, RecurringItem, SavingsGoal, Transaction

admin.site.register([Profile, Account, Category, Transaction, Budget, SavingsGoal, GoalContribution, RecurringItem, Debt, DebtPayment, Conversation, ChatMessage, AssistantPreference, AuditEntry])
