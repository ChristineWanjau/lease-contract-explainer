"""Seam 2: the clause splitter as a pure function (page texts in, chunks out)."""

from lce.splitter import split_clauses


def test_top_level_numbered_clauses_become_chunks_with_page_numbers():
    pages = ["1. Rent\nThe rent is 100 per month.\n2. Deposit\nA deposit of 200 is due."]

    chunks = split_clauses(pages)

    assert [(c.clause, c.page) for c in chunks] == [("1", 1), ("2", 1)]
    assert chunks[0].text.startswith("1. Rent")
    assert "rent is 100" in chunks[0].text
    assert "deposit of 200" in chunks[1].text


def test_dotted_sub_clauses_get_their_own_identifiers():
    pages = ["2. Payment\nTerms below.\n2.1 Rent\nDue monthly.\n2.2 Late Fees\n10 per day."]

    chunks = split_clauses(pages)

    assert [c.clause for c in chunks] == ["2", "2.1", "2.2"]


def test_clause_and_section_keywords_are_headings():
    pages = ["Clause 4 Termination\nEither party may end.\nSection 5 Notices\nIn writing."]

    chunks = split_clauses(pages)

    assert [c.clause for c in chunks] == ["4", "5"]
    assert chunks[1].text.startswith("Section 5")


def test_lettered_sub_items_stay_inside_their_parent_clause():
    pages = ["3. Tenant Duties\n(a) keep clean;\n(b) pay utilities.\n4. Landlord Duties\nRepairs."]

    chunks = split_clauses(pages)

    assert [c.clause for c in chunks] == ["3", "4"]
    assert "(a) keep clean" in chunks[0].text
    assert "(b) pay utilities" in chunks[0].text


def test_mixed_numbering_styles_in_one_document():
    pages = ["1. Parties\nA and B.\nClause 2 Term\nOne year.\n2.1 Renewal\nAutomatic."]

    chunks = split_clauses(pages)

    assert [c.clause for c in chunks] == ["1", "2", "2.1"]


def test_clause_spanning_a_page_break_keeps_its_starting_page():
    pages = ["1. Rent\nThe rent is", "100 per month.\n2. Deposit\n200."]

    chunks = split_clauses(pages)

    assert [(c.clause, c.page) for c in chunks] == [("1", 1), ("2", 2)]
    assert "100 per month" in chunks[0].text


def test_preamble_before_first_heading_is_kept_without_a_clause():
    pages = ["RESIDENTIAL LEASE\nBetween A and B.\n1. Rent\n100."]

    chunks = split_clauses(pages)

    assert [c.clause for c in chunks] == [None, "1"]
    assert "Between A and B" in chunks[0].text


def test_lines_starting_with_amounts_or_lowercase_are_not_headings():
    pages = ["1. Rent\nTotal due:\n1500 dollars each month\n2 weeks notice is required."]

    chunks = split_clauses(pages)

    assert [c.clause for c in chunks] == ["1"]


def test_unnumbered_text_falls_back_to_overlapping_fixed_size_chunks():
    sentence = "The tenant shall keep the premises clean and tidy. "
    pages = [sentence * 60]  # ~3000 chars, no headings

    chunks = split_clauses(pages)

    assert len(chunks) >= 3
    assert all(c.clause is None and c.page == 1 for c in chunks)
    # consecutive chunks overlap so no sentence is lost at a boundary
    assert chunks[0].text[-50:] in chunks[1].text


def test_every_chunk_text_appears_verbatim_in_the_source():
    pages = ["1. Rent\n  100 per month.\n(a) on the 1st", "2. Deposit\n200."]

    chunks = split_clauses(pages)

    source = "\n".join(pages)
    assert all(c.text in source for c in chunks)
