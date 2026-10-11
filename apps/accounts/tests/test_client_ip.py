"""Rate limits key on the visitor's real address, not one the visitor typed into X-Forwarded-For."""
from django.test import RequestFactory

from apps.accounts.services import client_ip


def test_edge_header_beats_a_typed_forwarded_for():
    rf = RequestFactory()
    req = rf.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 9.9.9.9", HTTP_CF_CONNECTING_IP="5.6.7.8")
    assert client_ip(req) == "5.6.7.8"
    assert client_ip(rf.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 9.9.9.9")) == "1.2.3.4"
    assert client_ip(rf.get("/", REMOTE_ADDR="10.0.0.1")) == "10.0.0.1"
