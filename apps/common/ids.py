"""Turn a posted / query-string id into an int, or None when it's empty or not a number.
filter(id=None) matches nothing and get(id=None) raises DoesNotExist, so views report
"not found" instead of crashing on filter(id="")."""


def pick_id(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
