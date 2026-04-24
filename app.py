from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from flask import Flask, jsonify, render_template, request, send_from_directory

try:
    from docx2pdf import convert as docx2pdf_convert
except ImportError:  # pragma: no cover - optional dependency at runtime
    docx2pdf_convert = None


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "template.docx"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DOCX = OUTPUT_DIR / "report.docx"
OUTPUT_PDF = OUTPUT_DIR / "report.pdf"
DOCX2PDF_TIMEOUT_SECONDS = 60
PHONE_PATTERN = re.compile(r"^\d{10}$")
LIBREOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, "g")
    return str(value).strip()


def safe_float(value: Any) -> float | None:
    text = stringify(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def calculate_bmi_value(height_cm: Any, weight_kg: Any) -> str:
    height = safe_float(height_cm)
    weight = safe_float(weight_kg)
    if height is None or weight is None or height <= 0 or weight <= 0:
        return ""

    bmi = weight / ((height / 100) ** 2)
    return f"{bmi:.2f}"


def normalize_payload(payload: dict[str, Any]) -> dict[str, str]:
    number = stringify(payload.get("number"))
    if number and not PHONE_PATTERN.fullmatch(number):
        raise ValueError("number must contain exactly 10 digits")

    return {
        "name": stringify(payload.get("name")),
        "age": stringify(payload.get("age")),
        "gender": stringify(payload.get("gender")),
        "number": number,
        "address": stringify(payload.get("address")),
        "height_cm": stringify(payload.get("height_cm")),
        "weight_kg": stringify(payload.get("weight_kg")),
        "pulse": stringify(payload.get("pulse")),
        "bp": stringify(payload.get("bp")),
        "rr": stringify(payload.get("rr")),
        "temp": stringify(payload.get("temp")),
        "blood_sugar": stringify(payload.get("blood_sugar")),
        "impression": stringify(payload.get("impression")),
    }


def build_placeholder_map(payload: dict[str, str]) -> dict[str, str]:
    return {
        "{{date}}": datetime.now().strftime("%d-%m-%Y"),
        "{{name}}": payload["name"],
        "{{age}}": payload["age"],
        "{{gender}}": payload["gender"],
        "{{number}}": payload["number"],
        "{{add}}": payload["address"],
        "{{ht}}": payload["height_cm"],
        "{{wt}}": payload["weight_kg"],
        "{{cat}}": calculate_bmi_value(payload["height_cm"], payload["weight_kg"]),
        "{{pul}}": payload["pulse"],
        "{{bp}}": payload["bp"],
        "{{rr}}": payload["rr"],
        "{{temp}}": payload["temp"],
        "{{bs}}": payload["blood_sugar"],
        "{{imp}}": payload["impression"],
    }


def replace_placeholders_in_text_nodes(text_nodes: list[Any], replacements: dict[str, str]) -> None:
    if not text_nodes:
        return

    for placeholder, replacement in replacements.items():
        while True:
            full_text = "".join(node.text or "" for node in text_nodes)
            start_index = full_text.find(placeholder)
            if start_index < 0:
                break

            end_index = start_index + len(placeholder)
            node_matches: list[tuple[int, int, int]] = []
            cursor = 0

            for node_index, node in enumerate(text_nodes):
                node_text = node.text or ""
                node_start = cursor
                node_end = cursor + len(node_text)
                cursor = node_end

                if node_end <= start_index or node_start >= end_index:
                    continue

                node_matches.append(
                    (
                        node_index,
                        max(start_index - node_start, 0),
                        min(end_index - node_start, len(node_text)),
                    )
                )

            if not node_matches:
                break

            first_node_index, first_start, _ = node_matches[0]
            last_node_index, _, last_end = node_matches[-1]

            if first_node_index == last_node_index:
                node = text_nodes[first_node_index]
                node_text = node.text or ""
                node.text = node_text[:first_start] + replacement + node_text[last_end:]
                continue

            first_node = text_nodes[first_node_index]
            last_node = text_nodes[last_node_index]
            first_text = first_node.text or ""
            last_text = last_node.text or ""

            first_node.text = first_text[:first_start] + replacement

            for node_index, _, _ in node_matches[1:-1]:
                text_nodes[node_index].text = ""

            last_node.text = last_text[last_end:]


def replace_placeholders_in_xml_root(root: Any, replacements: dict[str, str]) -> None:
    for paragraph in root.iter(qn("w:p")):
        text_nodes = [node for node in paragraph.iter(qn("w:t"))]
        replace_placeholders_in_text_nodes(text_nodes, replacements)


def replace_placeholders(document: Document, replacements: dict[str, str]) -> None:
    replace_placeholders_in_xml_root(document._element, replacements)

    for section in document.sections:
        replace_placeholders_in_xml_root(section.header._element, replacements)
        replace_placeholders_in_xml_root(section.footer._element, replacements)


def list_word_processes() -> list[str]:
    if os.name != "nt":
        return []

    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"],
        capture_output=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        text=True,
    )
    if result.returncode != 0:
        return []

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [line for line in lines if not line.startswith("INFO:")]


def find_libreoffice_binary() -> str | None:
    from_path = shutil.which("soffice") or shutil.which("libreoffice")
    if from_path:
        return from_path

    for candidate in LIBREOFFICE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def convert_with_word_com(docx_path: Path, pdf_path: Path) -> None:
    script = "\n".join(
        [
            "import sys",
            "import pythoncom",
            "from pathlib import Path",
            "from win32com.client import DispatchEx",
            "",
            "pythoncom.CoInitialize()",
            "word = DispatchEx('Word.Application')",
            "word.Visible = False",
            "word.DisplayAlerts = 0",
            "word.AutomationSecurity = 3",
            "doc = None",
            "src = str(Path(sys.argv[1]).resolve())",
            "dst = str(Path(sys.argv[2]).resolve())",
            "try:",
            "    doc = word.Documents.Open(",
            "        src,",
            "        ConfirmConversions=False,",
            "        ReadOnly=True,",
            "        AddToRecentFiles=False,",
            "        OpenAndRepair=True,",
            "    )",
            "    doc.ExportAsFixedFormat(",
            "        OutputFileName=dst,",
            "        ExportFormat=17,",
            "        OpenAfterExport=False,",
            "        OptimizeFor=0,",
            "        CreateBookmarks=0,",
            "    )",
            "finally:",
            "    if doc is not None:",
            "        doc.Close(False)",
            "    word.Quit()",
            "    pythoncom.CoUninitialize()",
        ]
    )
    command = [
        sys.executable,
        "-c",
        script,
        str(docx_path),
        str(pdf_path),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            creationflags=creationflags,
            text=True,
            timeout=DOCX2PDF_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Word COM export timed out. Close all Microsoft Word windows and try again."
        ) from exc

    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "unknown Word COM error"
        raise RuntimeError(f"Word COM export failed: {details}")

    if not pdf_path.exists():
        raise RuntimeError("Word COM export finished without creating the PDF file")


def convert_with_docx2pdf(docx_path: Path, pdf_path: Path) -> None:
    if docx2pdf_convert is None:
        raise RuntimeError("docx2pdf is not installed")

    command = [
        sys.executable,
        "-c",
        "from docx2pdf import convert; import sys; convert(sys.argv[1], sys.argv[2])",
        str(docx_path),
        str(pdf_path),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            creationflags=creationflags,
            text=True,
            timeout=DOCX2PDF_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "docx2pdf timed out while automating Microsoft Word. "
            "Close any blocked Word windows or install LibreOffice for the fallback path."
        ) from exc

    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "unknown docx2pdf error"
        raise RuntimeError(f"docx2pdf failed: {details}")

    if not pdf_path.exists():
        raise RuntimeError("docx2pdf finished without creating the PDF file")


def convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    conversion_errors: list[str] = []
    if pdf_path.exists():
        pdf_path.unlink()

    if os.name == "nt":
        try:
            convert_with_word_com(docx_path, pdf_path)
            return
        except Exception as exc:  # pragma: no cover - depends on local Office setup
            conversion_errors.append(str(exc))

        try:
            convert_with_docx2pdf(docx_path, pdf_path)
            return
        except Exception as exc:  # pragma: no cover - depends on local Office setup
            conversion_errors.append(str(exc))

    libreoffice_binary = find_libreoffice_binary()
    if libreoffice_binary:
        command = [
            libreoffice_binary,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_path.parent),
            str(docx_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0 and pdf_path.exists():
            return

        stderr = result.stderr.strip() or result.stdout.strip() or "unknown LibreOffice error"
        conversion_errors.append(f"LibreOffice failed: {stderr}")
    else:
        conversion_errors.append("LibreOffice/soffice is not installed")

    if os.name == "nt":
        word_processes = list_word_processes()
        if word_processes:
            conversion_errors.append(
                f"Microsoft Word appears to still be open ({len(word_processes)} WINWORD process(es)). "
                "Close every Word window, then retry."
            )

    raise RuntimeError("PDF conversion failed. " + " | ".join(conversion_errors))


def build_output_paths() -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return OUTPUT_DIR / f"report_{stamp}.docx", OUTPUT_DIR / f"report_{stamp}.pdf"


def refresh_latest_copies(source_docx: Path, source_pdf: Path) -> None:
    for source_path, target_path in ((source_docx, OUTPUT_DOCX), (source_pdf, OUTPUT_PDF)):
        try:
            shutil.copyfile(source_path, target_path)
        except OSError as exc:
            app.logger.warning("Could not refresh latest copy %s: %s", target_path.name, exc)


def generate_report_files(payload: dict[str, str]) -> tuple[Path, Path]:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_docx, output_pdf = build_output_paths()
    document = Document(str(TEMPLATE_PATH))
    replace_placeholders(document, build_placeholder_map(payload))
    document.save(str(output_docx))
    convert_docx_to_pdf(output_docx, output_pdf)
    refresh_latest_copies(output_docx, output_pdf)
    return output_docx, output_pdf


@app.post("/generate-report")
def generate_report():
    payload = request.get_json(silent=True)
    if payload is None or not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Request body must be valid JSON object",
                }
            ),
            400,
        )

    try:
        normalized_payload = normalize_payload(payload)
        _, pdf_path = generate_report_files(normalized_payload)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except FileNotFoundError as exc:
        app.logger.exception("Template error")
        return jsonify({"status": "error", "message": str(exc)}), 500
    except Exception as exc:  # pragma: no cover - integration/runtime path
        app.logger.exception("Failed to generate report")
        return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify({"status": "success", "pdf_url": f"/download/{pdf_path.name}"})


@app.get("/download/<path:filename>")
def download_file(filename: str):
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name
    if not file_path.exists():
        return jsonify({"status": "error", "message": "File not found"}), 404
    return send_from_directory(OUTPUT_DIR, safe_name, as_attachment=True)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ready",
            "message": "Mallika Hospital report service is ready",
        }
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("PORT") or os.getenv("FLASK_PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG", "1").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host=host, port=port, debug=debug)
