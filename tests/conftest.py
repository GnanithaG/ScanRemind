import pytest

from scanremind import create_app


class FakeMailer:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send(self, to, subject, body):
        if self.fail:
            raise RuntimeError("mail server down")
        self.sent.append({"to": to, "subject": subject, "body": body})


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(tmp_path / "test.db"),
            "MAIL_BACKEND": "console",
            "WTF_CSRF_ENABLED": False,
            "SESSION_COOKIE_SECURE": False,
            "APP_URL": "https://scanremind.example/set-reminder",
        }
    )
    app.extensions["mailer"] = FakeMailer()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mailer(app):
    return app.extensions["mailer"]


def login(client, email):
    with client.session_transaction() as session:
        session["verified_email"] = email
