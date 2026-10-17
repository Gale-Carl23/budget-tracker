from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from finance.models import BillNotification, LoginThrottle, RecurringItem
from finance.recurrence import recurring_occurrences


class Command(BaseCommand):
    help = "Create and email the 7-day, 3-day, and 1-day bill reminders."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report reminders without creating notifications or sending email.")

    def handle(self, *args, **options):
        today = timezone.localdate()
        dry_run = options["dry_run"]
        created_count = 0
        for item in RecurringItem.objects.filter(user__is_active=True, is_active=True, kind="bill").select_related("user", "account"):
            for days_before in (7, 3, 1):
                due_date = today + timedelta(days=days_before)
                if due_date not in recurring_occurrences(item, due_date, due_date):
                    continue
                if dry_run:
                    self.stdout.write(f"{item.user.email}: {item.name} due {due_date} ({days_before} day(s))")
                    continue
                notification, created = BillNotification.objects.get_or_create(
                    recurring_item=item,
                    due_date=due_date,
                    days_before=days_before,
                    defaults={"user": item.user, "amount": item.amount, "currency": item.account.currency},
                )
                created_count += int(created)

        sent_count = 0
        if not dry_run:
            pending = BillNotification.objects.filter(
                email_sent=False, email_attempts__lt=5,
                due_date__gte=today,
                recurring_item__is_active=True,
                user__is_active=True,
            ).select_related("user", "recurring_item", "recurring_item__account")
            for notification in pending.iterator(chunk_size=100):
                recipient = notification.user.email.strip()
                if not recipient:
                    continue
                days = notification.days_before
                due_text = notification.due_date.strftime("%B %d, %Y").replace(" 0", " ")
                subject = f"Nibi reminder: {notification.recurring_item.name} is due in {days} day{'s' if days != 1 else ''}"
                body = (
                    f"Hello {notification.user.get_username()},\n\n"
                    f"A bill you scheduled in Nibi is due in {days} day{'s' if days != 1 else ''}.\n\n"
                    f"{notification.recurring_item.name}\n"
                    f"Amount: {notification.currency} {notification.amount}\n"
                    f"Account: {notification.recurring_item.account.name}\n"
                    f"Due: {due_text}\n\n"
                    "Review your upcoming bills in Nibi. This is a reminder based on your schedule, not a payment.\n"
                )
                notification.email_attempts += 1
                try:
                    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
                except Exception as exc:
                    notification.save(update_fields=["email_attempts"])
                    self.stderr.write(f"Email failed for notification {notification.pk}: {type(exc).__name__}")
                    continue
                notification.email_sent = True
                notification.save(update_fields=["email_sent", "email_attempts"])
                sent_count += 1
            LoginThrottle.objects.filter(updated_at__lt=timezone.now() - timedelta(days=2)).delete()
        self.stdout.write(self.style.SUCCESS(f"Created {created_count} reminder(s); sent {sent_count} email(s)."))
