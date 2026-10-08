from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

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
    from .checklist import mark
    mark(request.company, "receipt_shared")
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
