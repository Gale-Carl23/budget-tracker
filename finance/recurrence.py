import calendar
from datetime import timedelta


def add_months(anchor, count):
    month_index = anchor.year * 12 + anchor.month - 1 + count
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return anchor.replace(year=year, month=month, day=min(anchor.day, calendar.monthrange(year, month)[1]))


def add_years(anchor, count):
    year = anchor.year + count
    return anchor.replace(year=year, day=min(anchor.day, calendar.monthrange(year, anchor.month)[1]))


def recurring_occurrences(item, start, end):
    anchor = item.next_date
    end = min(end, item.end_date) if item.end_date else end
    if anchor > end:
        return []
    dates = []
    if item.frequency == "weekly":
        jumps = max(0, (start - anchor).days // 7)
        current = anchor + timedelta(weeks=jumps)
        if current < start:
            current += timedelta(weeks=1)
        while current <= end:
            dates.append(current)
            current += timedelta(weeks=1)
    elif item.frequency == "monthly":
        jumps = max(0, (start.year - anchor.year) * 12 + start.month - anchor.month)
        current = add_months(anchor, jumps)
        if current < start:
            jumps += 1
            current = add_months(anchor, jumps)
        while current <= end:
            dates.append(current)
            jumps += 1
            current = add_months(anchor, jumps)
    else:
        jumps = max(0, start.year - anchor.year)
        current = add_years(anchor, jumps)
        if current < start:
            current = add_years(anchor, jumps + 1)
        if current <= end:
            dates.append(current)
    return dates


def next_recurring_date(current, frequency):
    if frequency == "weekly":
        return current + timedelta(weeks=1)
    if frequency == "monthly":
        return add_months(current, 1)
    return add_years(current, 1)
