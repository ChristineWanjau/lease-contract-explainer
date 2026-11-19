"""Generate the fictional sample lease PDF used by "Try sample" and tests.

Run: uv run python scripts/make_sample.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parents[1] / "src" / "lce" / "data" / "sample_lease.pdf"

PREAMBLE = [
    "SAMPLE RESIDENTIAL LEASE AGREEMENT",
    "FICTIONAL DOCUMENT FOR DEMONSTRATION ONLY. All names, places and figures are invented.",
    ("This Lease is made between Acme Property Holdings Ltd (the Landlord) and Jane Example (the Tenant) "
    "for the premises at Flat 4B, 12 Imaginary Road, Sampletown."),
]

PAGE_1 = [
    ("1. Term", "The lease begins on 1 January 2027 and ends on 31 December 2027."),
    ("2. Rent", "The Tenant shall pay rent of 1,200 per month, due on the 1st day of each month."),
    ("2.1 Late Payment", "Rent paid after the 5th day of the month incurs a late fee of 50 per day."),
    ("2.2 Rent Increase", "The Landlord may increase the rent at any time by giving the Tenant 14 days notice."),
    ("3. Security Deposit", "The Tenant shall pay a security deposit equal to three months rent."),
    (
        "3.1 Forfeiture",
        ("The Tenant shall forfeit the entire security deposit if the Tenant ends this lease for any reason "
        "before the end of the term, regardless of the condition of the premises."),
    ),
]

PAGE_2 = [
    (
        "4. Automatic Renewal",
        ("This lease shall automatically renew for a further twelve months unless the Tenant gives written "
        "notice of non-renewal at least 90 days before the end of the term."),
    ),
    (
        "5. Early Termination",
        ("If the Tenant ends this lease early, the Tenant shall pay an early termination fee equal to all "
        "remaining rent for the full term, in addition to any forfeiture under clause 3.1."),
    ),
    (
        "6. Repairs and Liability",
        ("The Tenant is responsible for all repairs to the premises, including structural repairs. "
        "The Tenant shall indemnify the Landlord against all claims, including those caused by the "
        "Landlord's own negligence."),
    ),
    ("7. Notices", "All notices must be in writing and delivered by registered post."),
    (
        "8. Changes to Terms",
        ("The Landlord may amend any term of this lease by notifying the Tenant. Continued occupation "
        "constitutes acceptance of the amended terms."),
    ),
    ("9. Governing Law", "This lease is governed by the laws of Sampletown."),
]


def build() -> None:
    styles = getSampleStyleSheet()
    story = [Paragraph(PREAMBLE[0], styles["Title"])]
    story += [Paragraph(p, styles["Normal"]) for p in PREAMBLE[1:]]
    story.append(Spacer(1, 12))
    for i, page in enumerate((PAGE_1, PAGE_2)):
        if i:
            story.append(PageBreak())
        for heading, body in page:
            story.append(Paragraph(f"<b>{heading}</b>", styles["Normal"]))
            story.append(Paragraph(body, styles["Normal"]))
            story.append(Spacer(1, 8))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(OUT), pagesize=A4, title="Sample Residential Lease").build(story)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
