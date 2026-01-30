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
    

@register.filter
def make_range(value):
    """Generate a range from 1 to value (inclusive)."""
    try:
        return range(1, int(value) + 1)
    except (ValueError, TypeError):
        return range(1, 6)  # Default to 5 if error


@register.filter
def subtract(value, arg):
    """Subtract arg from value."""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0
    

@register.simple_tag(takes_context=True)
def query_params(context):
    """
    Returns current query parameters as a string (for pagination links).
    Excludes 'page' parameter.
    """
    request = context['request']
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()

@register.simple_tag(takes_context=True)
def query_string(context, **kwargs):
    """
    Modify current query string with new values.
    Use empty string to remove a parameter.
    
    Usage: {% query_string search='' board_size='5' %}
    """
    request = context['request']
    params = request.GET.copy()
    
    for key, value in kwargs.items():
        if value == '':
            params.pop(key, None)
        else:
            params[key] = value
    
    params.pop('page', None)  # Reset to page 1 when filters change
    return params.urlencode()
