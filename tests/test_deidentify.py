from core.deidentify import redact, rehydrate_text


def test_redacts_labeled_client_name_and_matches_narrative_recurrence():
    text = (
        "Client Name: Jamie Rivera\n"
        "Client ID: TEST-001\n"
        "Session summary: Jamie Rivera had a productive session today. "
        "Jamie Rivera requested a break appropriately."
    )
    redacted, reverse_map = redact(text)

    assert "Jamie Rivera" not in redacted
    assert redacted.count("[CLIENT_NAME]") == 3  # label line + two narrative mentions
    assert reverse_map["[CLIENT_NAME]"] == "Jamie Rivera"


def test_does_not_confuse_client_id_or_diagnosis_with_client_name():
    text = "Client ID: TEST-002\nClient Diagnosis (ICD-10 Code): F84.0 Autistic disorder\nClient Name: Sam Lee"
    redacted, reverse_map = redact(text)

    assert reverse_map.get("[CLIENT_NAME]") == "Sam Lee"
    # The ID and diagnosis fields must not have been mistaken for the name.
    assert "TEST-002" not in reverse_map.values() or reverse_map.get("[CLIENT_ID]") == "TEST-002"
    assert "F84.0" in redacted  # diagnosis code itself isn't an identifier we redact


def test_redacts_dob_and_insurance_id_fields():
    text = "Date of Birth: 09/07/2019\nInsurance #: 9627938955"
    redacted, reverse_map = redact(text)

    assert "09/07/2019" not in redacted
    assert "9627938955" not in redacted
    assert reverse_map["[DOB]"] == "09/07/2019"
    assert reverse_map["[INSURANCE_ID]"] == "9627938955"


def test_redacts_freeform_email_phone_and_extra_dates():
    text = (
        "Contact the clinic at intake@example.com or (305) 614-1230.\n"
        "Next session scheduled for 09/01/2026."
    )
    redacted, reverse_map = redact(text)

    assert "intake@example.com" not in redacted
    assert "614-1230" not in redacted
    assert "09/01/2026" not in redacted
    assert any(v == "intake@example.com" for v in reverse_map.values())
    assert any(v == "09/01/2026" for v in reverse_map.values())


def test_does_not_redact_billing_codes_as_ids():
    text = "Billing Codes: 97153 (20), 97156 (4)"
    redacted, _ = redact(text)
    assert "97153" in redacted
    assert "97156" in redacted


def test_rehydrate_text_reverses_redaction_exactly():
    original = "Client Name: Alex Kim\nAlex Kim did well today."
    redacted, reverse_map = redact(original)
    assert rehydrate_text(redacted, reverse_map) == original


def test_rehydrate_text_handles_none_and_empty():
    assert rehydrate_text(None, {"[X]": "y"}) is None
    assert rehydrate_text("", {"[X]": "y"}) == ""
