"""Tests for cnc/tools/response_contracts.py."""

import pytest
from cnc.tools.response_contracts import (
    error_response,
    finding,
    merge_warnings_errors,
    normalize_exception_response,
    success_response,
)


# ---------------------------------------------------------------------------
# A) success_response
# ---------------------------------------------------------------------------


def test_success_response_ok_true():
    result = success_response()
    assert result["ok"] is True


def test_success_response_errors_empty():
    result = success_response()
    assert result["errors"] == []


def test_success_response_warnings_empty():
    result = success_response()
    assert result["warnings"] == []


def test_success_response_metadata_empty():
    result = success_response()
    assert result["metadata"] == {}


def test_success_response_data_none_by_default():
    result = success_response()
    assert result["data"] is None


def test_success_response_data_set():
    result = success_response(data={"x": 1})
    assert result["data"] == {"x": 1}


def test_success_response_warnings_set():
    result = success_response(warnings=["w1"])
    assert result["warnings"] == ["w1"]


def test_success_response_metadata_set():
    result = success_response(metadata={"tool_id": "drill_5mm"})
    assert result["metadata"]["tool_id"] == "drill_5mm"


def test_success_response_list_data():
    result = success_response(data=[1, 2, 3])
    assert result["data"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# B) error_response with string
# ---------------------------------------------------------------------------


def test_error_response_ok_false():
    result = error_response("something broke")
    assert result["ok"] is False


def test_error_response_string_becomes_list():
    result = error_response("something broke")
    assert isinstance(result["errors"], list)
    assert len(result["errors"]) == 1
    assert result["errors"][0] == "something broke"


def test_error_response_warnings_empty_by_default():
    result = error_response("err")
    assert result["warnings"] == []


def test_error_response_data_none_by_default():
    result = error_response("err")
    assert result["data"] is None


def test_error_response_metadata_empty_by_default():
    result = error_response("err")
    assert result["metadata"] == {}


# ---------------------------------------------------------------------------
# C) error_response with list
# ---------------------------------------------------------------------------


def test_error_response_list_unchanged():
    errors = ["e1", "e2"]
    result = error_response(errors)
    assert result["errors"] == ["e1", "e2"]


def test_error_response_list_two_errors():
    result = error_response(["first error", "second error"])
    assert len(result["errors"]) == 2


def test_error_response_with_warnings():
    result = error_response("err", warnings=["w1", "w2"])
    assert result["warnings"] == ["w1", "w2"]


def test_error_response_with_data():
    result = error_response("err", data={"tool": None})
    assert result["data"] == {"tool": None}


def test_error_response_with_metadata():
    result = error_response("err", metadata={"tool_id": "x"})
    assert result["metadata"]["tool_id"] == "x"


# ---------------------------------------------------------------------------
# D) normalize_exception_response
# ---------------------------------------------------------------------------


def test_normalize_exception_response_ok_false():
    result = normalize_exception_response(ValueError("bad input"))
    assert result["ok"] is False


def test_normalize_exception_response_data_none():
    result = normalize_exception_response(RuntimeError("oops"))
    assert result["data"] is None


def test_normalize_exception_response_errors_nonempty():
    result = normalize_exception_response(ValueError("bad"))
    assert len(result["errors"]) == 1


def test_normalize_exception_response_metadata_has_exception_type():
    result = normalize_exception_response(TypeError("wrong type"))
    assert result["metadata"]["exception_type"] == "TypeError"


def test_normalize_exception_response_context_prepended():
    result = normalize_exception_response(ValueError("oops"), context="get_tool_info")
    assert result["errors"][0].startswith("get_tool_info:")


def test_normalize_exception_response_no_context():
    result = normalize_exception_response(ValueError("standalone"))
    assert "standalone" in result["errors"][0]


def test_normalize_exception_response_warnings_empty():
    result = normalize_exception_response(OSError("file not found"))
    assert result["warnings"] == []


# ---------------------------------------------------------------------------
# E) merge_warnings_errors
# ---------------------------------------------------------------------------


def test_merge_warnings_errors_empty():
    result = merge_warnings_errors()
    assert result["warnings"] == []
    assert result["errors"] == []


def test_merge_warnings_errors_single_dict():
    d = {"warnings": ["w1"], "errors": ["e1"]}
    result = merge_warnings_errors(d)
    assert result["warnings"] == ["w1"]
    assert result["errors"] == ["e1"]


def test_merge_warnings_errors_two_dicts():
    d1 = {"warnings": ["w1"], "errors": ["e1"]}
    d2 = {"warnings": ["w2"], "errors": ["e2"]}
    result = merge_warnings_errors(d1, d2)
    assert "w1" in result["warnings"]
    assert "w2" in result["warnings"]
    assert "e1" in result["errors"]
    assert "e2" in result["errors"]


def test_merge_warnings_errors_missing_keys():
    d1 = {"warnings": ["w1"]}          # no errors key
    d2 = {"errors": ["e1"]}            # no warnings key
    result = merge_warnings_errors(d1, d2)
    assert result["warnings"] == ["w1"]
    assert result["errors"] == ["e1"]


def test_merge_warnings_errors_combined_count():
    d1 = {"warnings": ["w1", "w2"], "errors": []}
    d2 = {"warnings": ["w3"], "errors": ["e1"]}
    result = merge_warnings_errors(d1, d2)
    assert len(result["warnings"]) == 3
    assert len(result["errors"]) == 1


# ---------------------------------------------------------------------------
# F) finding helper
# ---------------------------------------------------------------------------


def test_finding_basic_keys():
    f = finding("error", "MISSING_FEEDRATE", "Feedrate not set")
    assert f["severity"] == "error"
    assert f["code"] == "MISSING_FEEDRATE"
    assert f["message"] == "Feedrate not set"


def test_finding_extra_keys():
    f = finding("warning", "SPINDLE_MISSING", "No spindle speed", line=5)
    assert f["line"] == 5


def test_finding_info_severity():
    f = finding("info", "UNIT_MM", "Program uses mm")
    assert f["severity"] == "info"
