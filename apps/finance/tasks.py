from celery import shared_task

from . import services


@shared_task
def run_daily_finance_jobs():
    """Creates due recurring invoices and sends cheque due-date reminders."""
    return {"invoices": services.run_all_recurring_invoices(), "cheque_reminders": services.send_cheque_reminders()}
