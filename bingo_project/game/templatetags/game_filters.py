from django import template

register = template.Library()

@register.filter
def split(value, delimiter=','):
    """Split string by delimiter."""
    if not value:
        return []
    return value.split(delimiter)