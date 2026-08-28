import pytest

from core.extraction import UnsupportedFileTypeError, extract_document_text
from tests.helpers import DOCUSIGN_BOILERPLATE_LINES, make_docx, make_pdf


def test_extract_pdf_strips_docusign_boilerplate(tmp_path):
    pdf_path = tmp_path / "note.pdf"
    make_pdf(
        pdf_path,
        pages=[
            [
                "Analyst Note - Caregiver Training",
                "Client: Test Client",
                "Visits: 8:15 am EDT to 10:15 am EDT (Provider Name) 97156",
                "Duration: 2:00",
                "Narrative: The caregiver practiced functional communication training.",
            ],
            DOCUSIGN_BOILERPLATE_LINES,
        ],
    )

    extracted = extract_document_text(pdf_path)

    assert extracted.docusign_stripped is True
    assert "97156" in extracted.full_text
    assert "functional communication" in extracted.full_text
    assert "Envelope Id" not in extracted.full_text
    assert "Certificate of Completion" not in extracted.full_text


def test_extract_pdf_without_boilerplate_is_untouched(tmp_path):
    pdf_path = tmp_path / "note.pdf"
    make_pdf(
        pdf_path,
        pages=[
            [
                "Billing Codes: 97153 (20)",
                "Summary: Services rendered at home.",
            ]
        ],
    )

    extracted = extract_document_text(pdf_path)

    assert extracted.docusign_stripped is False
    assert "97153" in extracted.full_text


def test_extract_docx_reads_paragraphs_and_tables(tmp_path):
    docx_path = tmp_path / "note.docx"
    make_docx(
        docx_path,
        paragraphs=["Session Note", "Narrative: services rendered at daycare."],
        tables=[[["Billing Codes:", "97155 (12)"]]],
    )

    extracted = extract_document_text(docx_path)

    assert "97155" in extracted.full_text
    assert "daycare" in extracted.full_text


def test_unsupported_file_type_raises(tmp_path):
    bogus_path = tmp_path / "note.txt"
    bogus_path.write_text("97153")

    with pytest.raises(UnsupportedFileTypeError):
        extract_document_text(bogus_path)


def test_legacy_doc_raises_helpful_error(tmp_path):
    doc_path = tmp_path / "note.doc"
    doc_path.write_bytes(b"not a real doc file")

    with pytest.raises(UnsupportedFileTypeError):
        extract_document_text(doc_path)
