from django import template
from django.utils.safestring import mark_safe

from apps.webapp.role_access import blocked_paths, can_open, strip_links

register = template.Library()


@register.filter(is_safe=True)
def hide_blocked(html, request):
    """{% filter hide_blocked:request %}…sidebar…{% endfilter %}: drops links the member's role can't open."""
    return mark_safe(strip_links(str(html), blocked_paths(request)))


@register.simple_tag(takes_context=True)
def can(context, url_name):
    """{% can 'analytics' as ok %}: may this member open that page?"""
    request = context.get("request")
    return bool(request and can_open(request, url_name))
