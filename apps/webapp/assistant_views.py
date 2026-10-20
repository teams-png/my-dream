"""Ask BookPilot page (see apps/webapp/assistant.py)."""
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _, gettext_lazy as _l

from . import assistant

ERRORS = {
    "limit": _l("Today's questions are used up. Ask again tomorrow."),
    "busy": _l("The assistant is busy right now. Please try again in a minute."),
    "refused": _l("The assistant can't answer that question."),
    "error": _l("Something went wrong. Please try again."),
}


@login_required
def ask(request):
    company = getattr(request, "company", None)
    if company is None or not assistant.enabled(company):
        raise Http404
    key = f"assistant_history_{company.id}"
    history = request.session.get(key, [])
    error = ""
    if request.method == "POST":
        if request.POST.get("clear"):
            request.session[key] = []
            return redirect("webapp:assistant")
        question = (request.POST.get("question") or "").strip()[:500]
        if question:
            answer, err = assistant.ask(company, question, [tuple(h) for h in history])
            if err:
                error = str(ERRORS[err])
            else:
                history = (history + [[question, answer]])[-5:]
                request.session[key] = history
                return redirect("webapp:assistant")
    return render(request, "webapp/assistant.html", {
        "history": history, "error": error,
        "left_text": _("Questions left today: %(n)s") % {"n": max(assistant.DAILY_LIMIT - assistant.used_today(company), 0)},
        "examples": [_("How were my sales this month compared with last month?"), _("Who owes me money?"),
                     _("Which products sell best this month?"), _("What should I reorder?")],
    })
