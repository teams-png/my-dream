from celery import shared_task
from .services import run_daily_expiry_check


@shared_task
def check_subscription_expiry():
    run_daily_expiry_check()
