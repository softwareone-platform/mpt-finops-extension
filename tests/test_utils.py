import asyncio
import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook

from ffc.utils import AsyncExcelWriter, extract_zip_files, read_excel_headers_and_rows


@pytest.fixture
def temp_dirs():
    safe = tempfile.TemporaryDirectory()
    attack = tempfile.TemporaryDirectory()
    extract = tempfile.TemporaryDirectory()
    yield safe.name, attack.name, extract.name
    safe.cleanup()
    attack.cleanup()
    extract.cleanup()

def create_safe_zip(zip_path):
    with zipfile.ZipFile(zip_path, "w") as zipf:
        zipf.writestr("safe.xlsx", "valid content")

def create_zip_slip_attack_zip(zip_path):
    with zipfile.ZipFile(zip_path, "w") as zipf:
        zipf.writestr("../../dangerous.xlsx", "dangerous content")

def create_safe_zip_excel_and_json_file(zip_path):
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_file_name = "test.xlsx"
        json_file_name_a = "test_a.json"
        json_file_name_b = "test_b.json"

        excel_path = os.path.join(temp_dir, zip_file_name)
        json_path_a = os.path.join(temp_dir, json_file_name_a)
        json_path_b = os.path.join(temp_dir, json_file_name_b)

        wb = Workbook()
        ws = wb.active
        ws.append(["ID", "Subscription Search Criteria", "Subscription Search Value",
                   "Item Search Criteria","Item Search Value","Usage Start Time",
                   "Usage End Time","Time", "Quantity", "Purchase Price", "Total Purchase Price",
                   "External Reference","Vendor Description 1", "Vendor Description 2",
                   "Vendor Reference"])
        ws.append([1,"subscription.externalIds.vendor","FORG-4801-6958-2949","item.externalIds.vendor",
                   "FIN-0001-P1M","29-Apr-2025","29-Apr-2025",1,0.00,0.00,"3d0fe384-b1cf","AWS SSO",
                   "6b1d3f21"])
        wb.save(excel_path)
        json_data = {'currency':"EUR", "value": 10.0}
        with open(json_path_a, "w", encoding="utf-8") as f:
            json.dump(json_data, f)
        with open(json_path_b, "w", encoding="utf-8") as f:
            json.dump(json_data, f)
        with zipfile.ZipFile(zip_path, "w") as zip_file:
            zip_file.write(excel_path, arcname=zip_file_name)
            zip_file.write(json_path_a, arcname=json_file_name_a)
            zip_file.write(json_path_b, arcname=json_file_name_b)

        return zip_path, temp_dir


def test_not_zip_file(temp_dirs):
    safe_dir, _, extract_to = temp_dirs
    zip_path = os.path.join(safe_dir, "safe.txt")
    create_safe_zip(zip_path)
    with pytest.raises(ValueError):
        extract_zip_files(zip_path,extract_to)

def test_safe_zip_extraction_success(temp_dirs):
    safe_dir, _, extract_to = temp_dirs
    zip_path = os.path.join(safe_dir, "safe.zip")
    create_safe_zip_excel_and_json_file(zip_path)

    try:
        xls_file, json_files = extract_zip_files(zip_path, extract_to)
        assert isinstance(xls_file, str)
        assert isinstance(json_files, list)
        assert os.path.exists(os.path.join(extract_to, "test.xlsx"))
    finally:
        shutil.rmtree(safe_dir)
        shutil.rmtree(extract_to)


def test_zip_slip_attack_is_blocked(temp_dirs, caplog):
    _, attack_dir, extract_to = temp_dirs
    zip_path = os.path.join(attack_dir, "attack.zip")
    create_zip_slip_attack_zip(zip_path)

    try:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(Exception) as excinfo:
                extract_zip_files(zip_path, extract_to)

            assert "WARNING: Unsafe zip entry" in str(excinfo.value)
        assert caplog.messages[0] == "Zip entry attempts to access another folder."
    finally:
        shutil.rmtree(attack_dir)
        shutil.rmtree(extract_to)

def test_read_excel_headers_and_rows_from_extracted_file(temp_dirs):
    safe_dir, _, extract_folder = temp_dirs
    zip_path = os.path.join(safe_dir, "safe.zip")
    create_safe_zip_excel_and_json_file(zip_path)
    excel_path, _ = extract_zip_files(zip_path, extract_folder)

    excel_path = os.path.join(extract_folder, excel_path)
    headers, rows = read_excel_headers_and_rows(excel_path)

    expected_headers = ["ID", "Subscription Search Criteria", "Subscription Search Value",
                        "Item Search Criteria", "Item Search Value", "Usage Start Time",
                        "Usage End Time", "Time", "Quantity", "Purchase Price",
                        "Total Purchase Price","External Reference",
                        "Vendor Description 1", "Vendor Description 2",
                        "Vendor Reference"]
    assert headers == expected_headers

    assert len(rows) >= 1
    assert rows[0][0] == 1
    assert rows[0][1] == "subscription.externalIds.vendor"



def test_read_excel_headers_and_rows_file_not_found(temp_dirs):
    with pytest.raises(FileNotFoundError):
        read_excel_headers_and_rows("/non/existent/path.xlsx")

def test_read_excel_headers_and_rows_invalid_excel_file(tmp_path, caplog):
    fake_path = tmp_path / "fake.xlsx"
    fake_path.write_text("The pen is on the table.")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(zipfile.BadZipFile) as excinfo:
            read_excel_headers_and_rows(str(fake_path))
        assert "The Excel file is invalid:" in str(excinfo.value)
    assert "The Excel file is invalid:" in caplog.messages[0]

def test_stop_iteration_empty_sheet(tmp_path, caplog):
    path = tmp_path / "empty.xlsx"
    # let's create an empty file
    wb = Workbook()
    wb.save(path)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError) as excinfo:
            read_excel_headers_and_rows(str(path))
        assert str(excinfo.value) == "The Excel file is empty or missing header row."
    assert "The Excel file is empty or missing header row." == caplog.messages[0]

@pytest.mark.asyncio
async def test_add_rows():
    headers = ["ID", "Subscription Search Criteria", "Subscription Search Value"]
    rows = ["10AB", "test", "AUT-123-123-123"]
    with TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.xlsx"

        writer = AsyncExcelWriter(default_buffer_size=1)

        with patch.object(writer, "_write_rows", new_callable=MagicMock) as mock_write:
            async with writer:
                await writer.add_rows(str(file_path), headers, rows)

            mock_write.assert_called_once()
            args = mock_write.call_args[0]
            assert Path(args[0]) == file_path
            assert args[1] == headers
            assert args[2] == rows

@pytest.mark.asyncio
async def test_flush_all_writes_multiple_files():
    headers = ["ID", "Subscription Search Criteria", "Subscription Search Value"]
    rows = ["10AB", "test", "AUT-123-123-123"]

    with TemporaryDirectory() as tmpdir:
        file1 = str(Path(tmpdir) / "charge_file1.xlsx")
        file2 = str(Path(tmpdir) / "charge_file2.xlsx")

        writer = AsyncExcelWriter(default_buffer_size=10)

        with patch.object(writer, "_write_rows", new_callable=MagicMock) as mock_write:
            async with writer:
                await writer.add_rows(file1, headers, rows)
                await writer.add_rows(file2, headers, rows)
                await writer.flush_all()

            assert mock_write.call_count == 2
            all_paths = {call.args[0] for call in mock_write.call_args_list}
            assert Path(file1) in all_paths
            assert Path(file2) in all_paths


@pytest.mark.asyncio
async def test_flush_skips_empty_buffers():
    writer = AsyncExcelWriter(default_buffer_size=1)
    file_path = "/tmp/empty.xlsx"

    writer._buffers[file_path] = []

    with patch.object(writer, "_write_rows", new_callable=MagicMock) as mock_write:
        await writer._flush(Path(file_path))
        mock_write.assert_not_called()

def test_write_rows_raises_os_error_on_save():
    writer = AsyncExcelWriter()
    path = Path("/tmp/test.xlsx")
    headers = ["ID", "Subscription Search Criteria", "Subscription Search Value"]
    rows = ["10AB", "test", "AUT-123-123-123"]

    with patch("openpyxl.workbook.workbook.Workbook.save", side_effect=RuntimeError("Disk error")):
        with pytest.raises(OSError) as exc_info:
            writer._write_rows(path, headers, rows)

        assert "Failed to add content to Excel file" in str(exc_info.value)

def test_get_lock_returns_lock_instance():
    writer = AsyncExcelWriter()
    file_path = "/tmp/test1.xlsx"

    lock = writer._get_lock(file_path)
    assert isinstance(lock, asyncio.Lock)

def test_get_lock_returns_same_lock_for_same_path():
    writer = AsyncExcelWriter()
    file_path = "/tmp/test2.xlsx"

    lock1 = writer._get_lock(file_path)
    lock2 = writer._get_lock(file_path)

    assert lock1 is lock2

def test_get_lock_returns_different_locks_for_different_paths():
    writer = AsyncExcelWriter()

    lock1 = writer._get_lock("/tmp/a.xlsx")
    lock2 = writer._get_lock("/tmp/b.xlsx")

    assert lock1 is not lock2

