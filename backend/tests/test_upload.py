"""Seam 1: uploading your own PDF (#3)."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from lce.app import create_app


def make_pdf(pages: list[str]) -> bytes:
    """Build a PDF with one page per string; an empty string makes a page with no text."""
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    for text in pages:
        y = 800
        for line in text.split("\n"):
            pdf.drawString(50, y, line)
            y -= 14
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        llm=FakeListChatModel(responses=["unused"]),
        embeddings=DeterministicFakeEmbedding(size=16),
    )
    return TestClient(app)


def upload(client: TestClient, data: bytes, filename="contract.pdf", content_type="application/pdf"):
    return client.post("/api/upload", files={"file": (filename, data, content_type)})


def test_a_text_pdf_creates_a_session_with_its_clauses(client):
    pdf = make_pdf(["1. Term\nOne year.\n2. Rent\n500 per month.", "3. Deposit\nTwo months."])

    response = upload(client, pdf)

    assert response.status_code == 200
    body = response.json()
    assert [(c["clause"], c["page"]) for c in body["chunks"]] == [("1", 1), ("2", 1), ("3", 2)]
    fetched = client.get(f"/api/sessions/{body['session_id']}")
    assert fetched.status_code == 200


def test_a_non_pdf_is_rejected(client):
    response = upload(client, b"hello, not a pdf", filename="notes.txt", content_type="text/plain")

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "not_pdf"


def test_a_file_named_pdf_that_is_not_a_pdf_is_rejected(client):
    response = upload(client, b"just text pretending", filename="fake.pdf")

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "not_pdf"


def test_a_pdf_with_too_many_pages_is_rejected(client):
    pdf = make_pdf([f"{i}. Clause\nText." for i in range(1, 32)])

    response = upload(client, pdf)

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["code"] == "too_many_pages"
    assert "30" in detail["message"]


def test_a_file_over_the_size_limit_is_rejected(client):
    big = b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 1)

    response = upload(client, big)

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["code"] == "too_large"
    assert "10 MB" in detail["message"]


def test_a_pdf_without_extractable_text_is_rejected_as_a_scan(client):
    response = upload(client, make_pdf(["", ""]))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "scanned_pdf"
    assert "scanned" in detail["message"].lower()


def test_a_corrupt_pdf_is_rejected_cleanly(client):
    response = upload(client, b"%PDF-1.4\nthis is broken")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unreadable_pdf"
