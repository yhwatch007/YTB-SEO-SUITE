from django import template

register = template.Library()

@register.filter(name="shortnum")
def shortnum(value):
    """
    0 -> 0
    4300 -> 4.3k
    1250000 -> 1.3M
    2500000000 -> 2.5B
    """
    try:
        n = float(value)
    except (TypeError, ValueError):
        return value

    absn = abs(n)
    if absn < 1_000:
        return f"{int(n)}"
    elif absn < 1_000_000:
        return f"{n/1_000:.1f}k".rstrip("0").rstrip(".") + "k"
    elif absn < 1_000_000_000:
        return f"{n/1_000_000:.1f}M".rstrip("0").rstrip(".") + "M"
    else:
        return f"{n/1_000_000_000:.1f}B".rstrip("0").rstrip(".") + "B"
