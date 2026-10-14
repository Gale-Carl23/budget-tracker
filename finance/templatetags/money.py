from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()
SYMBOLS = {"USD": "$", "PHP": "₱", "EUR": "€", "GBP": "£", "CNY": "¥", "JPY": "¥", "CAD": "CA$", "AUD": "A$"}

@register.filter
def money(value, currency="USD"):
    try:
        amount = Decimal(str(value or 0))
        formatted = f"{amount:,.2f}"
    except (InvalidOperation, ValueError, TypeError):
        formatted = "0.00"
    code = str(currency or "USD").upper()
    symbol = SYMBOLS.get(code)
    return f"{symbol}{formatted}" if symbol else f"{code} {formatted}"
