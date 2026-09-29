from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.sales import sharing
from apps.sales.models import SalesInvoice


class EmailInvoiceForm(forms.Form):
    email = forms.EmailField(label="Customer email")
    note = forms.CharField(label="Message (optional)", required=False, max_length=1000,
                           widget=forms.Textarea(attrs={"rows": 3}))


def _public_url(request, invoice):
    return request.build_absolute_uri(reverse("webapp:public_invoice", args=[sharing.share_token(invoice)]))


@login_required
def invoice_share(request, invoice_id):
    if getattr(request, "company", None) is None:
        raise Http404
    invoice = get_object_or_404(SalesInvoice.objects.for_company(request.company).select_related("customer"), id=invoice_id)
    url = _public_url(request, invoice)
    form = EmailInvoiceForm(request.POST or None, initial={"email": invoice.customer.email})
    if request.method == "POST" and form.is_valid():
        try:
            as_pdf = sharing.email_invoice(invoice, to=form.cleaned_data["email"], url=url, note=form.cleaned_data["note"])
        except Exception as exc:  # SMTP not configured / rejected
            messages.error(request, f"Email could not be sent: {exc}. Check the email settings (EMAIL_HOST etc.).")
        else:
            from apps.audit.services import log_action
            log_action(company=request.company, user=request.user, action="email", model_name="SalesInvoice",
                       object_id=invoice.id, changes={"to": form.cleaned_data["email"]})
            messages.success(request, f"Invoice emailed to {form.cleaned_data['email']}"
                                      + ("" if as_pdf else " (as a web page attachment)") + ".")
            return redirect("webapp:invoice_share", invoice_id=invoice.id)
    return render(request, "webapp/invoice_share.html", {
        "invoice": invoice, "form": form, "public_url": url,
        "whatsapp_url": sharing.whatsapp_url(invoice, url),
        "whatsapp_any_url": sharing.whatsapp_url(invoice, url, phone=""),
        "message": sharing.share_message(invoice, url),
    })


@xframe_options_sameorigin
def public_invoice(request, token):
    """Customer-facing invoice page; no login, protected by the signed token."""
    invoice = sharing.invoice_from_token(token)
    if invoice is None:
        raise Http404("This invoice link is invalid or has expired.")
    if request.GET.get("format") == "pdf":
        pdf = sharing.render_invoice_pdf(invoice)
        if pdf:
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{invoice.invoice_number}.pdf"'
            return response
    response = HttpResponse(sharing.render_invoice_html(invoice, public_url=request.build_absolute_uri()))
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response
