"""Offline model availability must fail before attempting OCR or downloads."""
from pathlib import Path

import pytest
from edw_worker.attachment_parser_process import ocr_image


def test_missing_model_weights_are_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr(Path, 'is_file', lambda _self: False)
    with pytest.raises(ImportError, match='OCR model unavailable'):
        ocr_image(b'not an image')
