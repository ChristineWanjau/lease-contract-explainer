"""Generate the fictional sample PDFs used by "Try sample" and tests.

Run: uv run python scripts/make_sample.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

DATA = Path(__file__).resolve().parents[1] / "src" / "lce" / "data"
OUT = DATA / "sample_lease.pdf"

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

# Fictional Kenyan employment contract. Planted contract risks (one per #16 category
# where natural): probation, termination without a hearing, non-compete, deductions,
# unpaid overtime, transfer, unilateral changes, ownership of work. The leave and
# notice figures are deliberately low for the legal-rule checks in a later ticket.
EMPLOYMENT_OUT = DATA / "sample_employment_ke.pdf"

EMPLOYMENT_PREAMBLE = [
    "SAMPLE CONTRACT OF EMPLOYMENT",
    "FICTIONAL DOCUMENT FOR DEMONSTRATION ONLY. All names, places and figures are invented.",
    (
        "This Contract is made between Example Traders Ltd of P.O. Box 00000, Nairobi "
        "(the Employer) and Jane Example, ID No. 00000000 (the Employee)."
    ),
]

EMPLOYMENT_PAGE_1 = [
    (
        "1. Position and Start Date",
        "The Employee is employed as an Accounts Assistant starting on 1 February 2027.",
    ),
    (
        "2. Probation",
        (
            "The first twelve months of employment are a probationary period, which the Employer "
            "may extend at its sole discretion. During probation either party may end this "
            "contract without notice."
        ),
    ),
    (
        "3. Salary",
        "The Employee shall be paid a gross salary of KES 60,000 per month, payable in arrears.",
    ),
    (
        "3.1 Deductions",
        (
            "The Employer may deduct from the Employee's salary any amount the Employer considers "
            "owed by the Employee, including the cost of any lost or damaged company property."
        ),
    ),
    (
        "4. Working Hours",
        (
            "Normal working hours are 8am to 5pm, Monday to Saturday. The Employee shall work such "
            "additional hours as the business requires, and the salary covers all hours worked."
        ),
    ),
    ("5. Annual Leave", "The Employee is entitled to 14 working days of paid annual leave per year."),
]

EMPLOYMENT_PAGE_2 = [
    (
        "6. Place of Work",
        (
            "The Employee's place of work is Nairobi. The Employer may transfer the Employee to any "
            "branch in Kenya at any time, and the Employee shall bear the cost of relocating."
        ),
    ),
    (
        "7. Termination",
        (
            "After probation, either party may end this contract by giving 7 days written notice. "
            "The Employer may dismiss the Employee summarily for any reason it considers "
            "sufficient, without a hearing."
        ),
    ),
    (
        "8. Confidentiality and Non-Competition",
        (
            "For three years after this contract ends, the Employee shall not work for or start any "
            "business in Kenya that competes with the Employer."
        ),
    ),
    (
        "9. Intellectual Property",
        (
            "Everything the Employee creates, whether during working hours or not, belongs to the "
            "Employer."
        ),
    ),
    (
        "10. Changes to this Contract",
        "The Employer may change any term of this contract by posting a notice at the workplace.",
    ),
    ("11. Governing Law", "This contract is governed by the laws of Kenya."),
]


def _write(out: Path, title: str, preamble: list[str], pages: tuple[list, ...]) -> None:
    styles = getSampleStyleSheet()
    story = [Paragraph(preamble[0], styles["Title"])]
    story += [Paragraph(p, styles["Normal"]) for p in preamble[1:]]
    story.append(Spacer(1, 12))
    for i, page in enumerate(pages):
        if i:
            story.append(PageBreak())
        for heading, body in page:
            story.append(Paragraph(f"<b>{heading}</b>", styles["Normal"]))
            story.append(Paragraph(body, styles["Normal"]))
            story.append(Spacer(1, 8))
    out.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out), pagesize=A4, title=title).build(story)
    print(f"wrote {out}")


def build() -> None:
    _write(OUT, "Sample Residential Lease", PREAMBLE, (PAGE_1, PAGE_2))
    _write(
        EMPLOYMENT_OUT,
        "Sample Contract of Employment",
        EMPLOYMENT_PREAMBLE,
        (EMPLOYMENT_PAGE_1, EMPLOYMENT_PAGE_2),
    )


if __name__ == "__main__":
    build()
