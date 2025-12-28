from django import template

register = template.Library()

@register.filter
def split(value, delimiter=','):
    """Split string by delimiter."""
    if not value:
        return []
    return value.split(delimiter)


@register.filter
def replacewith(value, args):
    old, new = args.split(',')
    return value.replace(old, new)


@register.filter
def multiply(value, arg):
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return ''