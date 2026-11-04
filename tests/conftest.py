import os
import sys

# App modules import as ``utils.x`` / ``models.x`` with src/ on the path,
# matching how streamlit run src/web_app.py and src/main.py execute.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# These tests use local fixtures and fake notifiers. Never inherit service
# credentials from a developer shell or a future CI configuration.
for name in (
    "SUPABASE_URL", "SUPABASE_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER", "EMAIL_ADDRESS", "EMAIL_PASSWORD", "MEDSYNC_DEV_SHOW_OTP",
    "MEDSYNC_LOCAL_DEMO",
):
    os.environ[name] = ""
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import socket
import pytest


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not open network connections")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
