"""URLs served on a client's own domain: the website plus the public forms and feeds it uses."""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from . import site_views
from .urls import urlpatterns as app_urlpatterns

PUBLIC = {"kit_info", "kit_catalogue", "kit_offers", "kit_enquiry", "kit_enquiry_js", "kit_catalogue_js",
          "book_page", "book_options", "book_form_js", "book_submit",
          "careers_home", "careers_job", "careers_apply", "careers_thanks", "careers_jobs_json", "careers_form_js",
          "site_public"}

public_patterns = [p for p in app_urlpatterns if getattr(p, "name", None) in PUBLIC]
public_patterns.append(path("", site_views.site_domain_home, name="site_domain_home"))

urlpatterns = [path("", include((public_patterns, "webapp")))]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
