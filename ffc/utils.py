import logging
import os
import zipfile

from openpyxl import load_workbook
from openpyxl.cell import Cell

logger = logging.getLogger(__name__)
def find_first(func, iterable, default=None): # pragma no cover
    return next(filter(func, iterable), default)


def extract_zip_files(file_path, extract_folder)-> tuple[str, list[str]]:
    """
    This function securely zip files from a zip archive into the
    given extract_folder.

    It also prevents Zip Slip attacks by validating that all extracted paths
    remain within the specified extraction directory.

    Args:
        file_path (str): Path to the .zip archive file.
        extract_folder (str): Directory where the archive should be extracted.

    Returns:
        List[str]: List of  filenames located directly in the `extract_folder`
        directory.

    Raises:
        Exception: If a zip entry attempts to escape the extraction directory (Zip Slip).

    """
    if not file_path.lower().endswith(".zip"):
        raise ValueError(f"{file_path} is not a zip archive.")

    with zipfile.ZipFile(file_path, "r") as zip_ref:
        for item in zip_ref.namelist():
            # ensure we are in the right path
            item_path = os.path.abspath(os.path.join(extract_folder, item))
            if not item_path.startswith(os.path.abspath(extract_folder)):
                logger.exception("Zip entry attempts to access another folder.")
                raise Exception(f"WARNING: Unsafe zip entry: {item}")
            zip_ref.extract(item, extract_folder)

    xlsx_file = ""
    json_files = []

    for f in os.listdir(extract_folder):
        full_path = os.path.join(extract_folder, f)
        if (f.endswith(".xlsx") and not f.startswith("~") and
                os.path.isfile(os.path.join(extract_folder, f))):
            xlsx_file = full_path
        elif f.endswith(".json"):
            json_files.append(full_path)
    return xlsx_file, json_files


def read_excel_headers_and_rows(excel_path)->tuple[list[str], list[tuple[Cell, ...]]]:
    """
    This function reads the headers and data rows from an Excel (.xlsx) file.

    Args:
        excel_path (str): Path to the Excel file to read.

    Returns:
        tuple[list[str], list[tuple]]: A tuple containing a list of header values and a list
        of data rows.

    Raises:
        FileNotFoundError: If the file does not exist or is not accessible.
        InvalidFileException: If the file exists but is not a valid Excel (.xlsx) file.
        ValueError: If the Excel file is empty or missing a header row.
    """

    if not os.path.isfile(excel_path):
        raise FileNotFoundError(f"File not found: {excel_path}")
    try:
        workbook = load_workbook(excel_path, read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(min_row=2))  # here there's the actual data
        headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
        return headers, rows
    except zipfile.BadZipFile:
        logger.exception(f"The Excel file is invalid: {excel_path}")
        raise zipfile.BadZipFile(f"The Excel file is invalid: {excel_path}")
    except StopIteration:
        logger.exception("The Excel file is empty or missing header row.")
        raise ValueError("The Excel file is empty or missing header row.")

#
#
# x, j = extract_zip_files(file_path="/Users/hellbreak/Downloads/FCHG-8316-5287-0835.zip", extract_folder="/Users/hellbreak/Downloads/TEST_FOLDER")
# print(x,j)
