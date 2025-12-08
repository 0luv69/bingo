from django import template

register = template.Library()


@register.filter
def split(value, delimiter=','):
    """
    Split a string by delimiter. 
    Usage: {{ "1,2,3"|split:"," }}
    Returns: ['1', '2', '3']
    """
    if not value:
        return []
    return value.split(delimiter)


@register.filter
def get_item(lst, index):
    """
    Get item from list by index.
    Usage: {{ mylist|get_item:0 }}
    """
    try:
        return lst[int(index)]
    except (IndexError, TypeError, ValueError):
        return None


@register.filter
def add_int(value, arg):
    """
    Convert string to int and add. 
    Usage: {{ "5"|add_int:0 }} → 5 (as integer)
    """
    try:
        return int(value) + int(arg)
    except (ValueError, TypeError):
        return value