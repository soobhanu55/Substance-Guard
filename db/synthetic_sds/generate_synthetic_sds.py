"""Generates a synthetic set of 26 supplier SDS / material test-report PDFs, mixing
clearly compliant, clearly non-compliant, borderline (within the +/-10% threshold band),
and ambiguous/missing-CAS cases -- all built from REAL substances and REAL thresholds in
db/regulatory_data/*.json, so the ground-truth labels below are independently checkable
against the actual graph, not invented numbers.

Run: python db/synthetic_sds/generate_synthetic_sds.py
"""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

OUT_DIR = Path(__file__).resolve().parent / "pdfs"
GROUND_TRUTH_PATH = Path(__file__).resolve().parent / "ground_truth.json"

# Each doc: id, product_name, manufacturer, doc_type, components: list of
# {component_name, substance_name, cas_number|None, concentration, unit,
#  expected_status, expected_reason_code}
DOCS = [
    # --- clearly compliant (1-6) ---
    {"id": "doc-01", "product_name": "Standard USB Charging Cable", "manufacturer": "Voltera Ltd",
     "doc_type": "SDS", "case": "clearly_compliant", "components": [
        {"component_name": "Cable Insulation", "substance_name": "Dibutyl phthalate (DBP)", "cas_number": "84-74-2",
         "concentration": 0.02, "unit": "pct", "expected_status": "COMPLIANT", "expected_reason_code": "within_threshold"},
        {"component_name": "Connector Solder", "substance_name": "Lead", "cas_number": "7439-92-1",
         "concentration": 0.03, "unit": "pct", "expected_status": "COMPLIANT", "expected_reason_code": "within_threshold"},
    ]},
    {"id": "doc-02", "product_name": "Outdoor Sensor Enclosure", "manufacturer": "Sensatek Inc",
     "doc_type": "Test Report", "case": "clearly_compliant", "components": [
        {"component_name": "Weatherproof Coating", "substance_name": "Perfluorooctanoic acid (PFOA)", "cas_number": "335-67-1",
         "concentration": 18, "unit": "ppb", "expected_status": "COMPLIANT", "expected_reason_code": "within_threshold"},
    ]},
    {"id": "doc-03", "product_name": "Children's Building Block Set", "manufacturer": "PlayCorp",
     "doc_type": "SDS", "case": "clearly_compliant", "components": [
        {"component_name": "Plastic Blocks", "substance_name": "Boric acid", "cas_number": "10043-35-3",
         "concentration": 0.01, "unit": "pct", "expected_status": "COMPLIANT", "expected_reason_code": "within_threshold"},
        {"component_name": "Paint Coating", "substance_name": "Cadmium", "cas_number": "7440-43-9",
         "concentration": 0.002, "unit": "pct", "expected_status": "COMPLIANT", "expected_reason_code": "within_threshold"},
    ]},
    {"id": "doc-04", "product_name": "Textile Water-Repellent Jacket", "manufacturer": "AlpineWear",
     "doc_type": "Test Report", "case": "clearly_compliant", "components": [
        {"component_name": "DWR Fabric Treatment", "substance_name": "1H,1H,2H,2H-Perfluorooctane sulfonic acid", "cas_number": "27619-97-2",
         "concentration": 5, "unit": "ppb", "expected_status": "COMPLIANT", "expected_reason_code": "within_threshold"},
    ]},
    {"id": "doc-05", "product_name": "Kitchen Utensil Handle", "manufacturer": "HomeGoods Co",
     "doc_type": "SDS", "case": "clearly_compliant", "components": [
        {"component_name": "Silicone Grip", "substance_name": "Mercury", "cas_number": "7439-97-6",
         "concentration": 0.001, "unit": "pct", "expected_status": "COMPLIANT", "expected_reason_code": "within_threshold"},
    ]},
    {"id": "doc-06", "product_name": "Laptop Bottom Case", "manufacturer": "Compucase Ltd",
     "doc_type": "Test Report", "case": "clearly_compliant", "components": [
        {"component_name": "Recycled ABS Housing", "substance_name": "Bis(2-ethylhexyl) phthalate (DEHP)", "cas_number": "117-81-7",
         "concentration": 0.015, "unit": "pct", "expected_status": "COMPLIANT", "expected_reason_code": "within_threshold"},
    ]},

    # --- clearly non-compliant (7-15) ---
    {"id": "doc-07", "product_name": "Industrial Metal Coating Spray", "manufacturer": "Acme Coatings Inc",
     "doc_type": "SDS", "case": "clearly_non_compliant", "components": [
        {"component_name": "Weatherproof Coating", "substance_name": "Perfluorooctanoic acid (PFOA)", "cas_number": "335-67-1",
         "concentration": 500, "unit": "ppb", "expected_status": "NON_COMPLIANT", "expected_reason_code": "exceeds_threshold"},
    ]},
    {"id": "doc-08", "product_name": "Consumer Electronics Cable Set", "manufacturer": "Voltera Ltd",
     "doc_type": "Test Report", "case": "clearly_non_compliant", "components": [
        {"component_name": "Wire Insulation", "substance_name": "Dibutyl phthalate (DBP)", "cas_number": "84-74-2",
         "concentration": 0.45, "unit": "pct", "expected_status": "NON_COMPLIANT", "expected_reason_code": "exceeds_threshold"},
    ]},
    {"id": "doc-09", "product_name": "Toy Figurine Paint Set", "manufacturer": "PlayCorp",
     "doc_type": "SDS", "case": "clearly_non_compliant", "components": [
        {"component_name": "Yellow Paint Pigment", "substance_name": "Lead chromate", "cas_number": "7758-97-6",
         "concentration": 3.2, "unit": "pct", "expected_status": "NON_COMPLIANT", "expected_reason_code": "exceeds_threshold"},
    ]},
    {"id": "doc-10", "product_name": "Firefighting Foam Concentrate", "manufacturer": "GuardFoam Systems",
     "doc_type": "Test Report", "case": "clearly_non_compliant", "components": [
        {"component_name": "Foam Concentrate", "substance_name": "Perfluorooctanesulfonic acid (PFOS)", "cas_number": "1763-23-1",
         "concentration": 1200, "unit": "ppb", "expected_status": "NON_COMPLIANT", "expected_reason_code": "exceeds_threshold"},
    ]},
    {"id": "doc-11", "product_name": "Vinyl Flooring Tile", "manufacturer": "FloorTech Industries",
     "doc_type": "SDS", "case": "clearly_non_compliant", "components": [
        {"component_name": "Vinyl Plasticizer Layer", "substance_name": "Bis(2-ethylhexyl) phthalate (DEHP)", "cas_number": "117-81-7",
         "concentration": 1.1, "unit": "pct", "expected_status": "NON_COMPLIANT", "expected_reason_code": "exceeds_threshold"},
    ]},
    {"id": "doc-12", "product_name": "Automotive Wiring Harness", "manufacturer": "AutoWire GmbH",
     "doc_type": "Test Report", "case": "clearly_non_compliant", "components": [
        {"component_name": "Harness Solder Joint", "substance_name": "Cadmium", "cas_number": "7440-43-9",
         "concentration": 0.08, "unit": "pct", "expected_status": "NON_COMPLIANT", "expected_reason_code": "exceeds_threshold"},
    ]},
    {"id": "doc-13", "product_name": "Printed Circuit Board Assembly", "manufacturer": "Compucase Ltd",
     "doc_type": "SDS", "case": "clearly_non_compliant", "components": [
        {"component_name": "PCB Flame Retardant Layer", "substance_name": "Decabromodiphenyl ether (DecaBDE)", "cas_number": "1163-19-5",
         "concentration": 0.6, "unit": "pct", "expected_status": "NON_COMPLIANT", "expected_reason_code": "exceeds_threshold"},
    ]},
    {"id": "doc-14", "product_name": "Plastic Food Container", "manufacturer": "HomeGoods Co",
     "doc_type": "Test Report", "case": "clearly_non_compliant", "components": [
        {"component_name": "Container Body", "substance_name": "Bisphenol A", "cas_number": "80-05-7",
         "concentration": 1.5, "unit": "pct", "expected_status": "NON_COMPLIANT", "expected_reason_code": "exceeds_threshold"},
    ]},
    {"id": "doc-15", "product_name": "Semiconductor Etching Solution", "manufacturer": "ChipProcess Materials",
     "doc_type": "Test Report", "case": "clearly_non_compliant", "components": [
        {"component_name": "Etch Residue Rinse", "substance_name": "Hexafluoropropylene oxide dimer acid (GenX)", "cas_number": "13252-13-6",
         "concentration": 300, "unit": "ppb", "expected_status": "NON_COMPLIANT", "expected_reason_code": "exceeds_threshold"},
    ]},

    # --- borderline, within +/-10% band (16-21) ---
    {"id": "doc-16", "product_name": "Solder Paste Reel", "manufacturer": "AutoWire GmbH",
     "doc_type": "Test Report", "case": "borderline", "components": [
        {"component_name": "Solder Joint", "substance_name": "Lead", "cas_number": "7439-92-1",
         "concentration": 0.105, "unit": "pct", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "borderline_concentration"},
    ]},
    {"id": "doc-17", "product_name": "Anti-Corrosion Primer", "manufacturer": "Acme Coatings Inc",
     "doc_type": "SDS", "case": "borderline", "components": [
        {"component_name": "Primer Base", "substance_name": "Anthracene", "cas_number": "120-12-7",
         "concentration": 0.098, "unit": "pct", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "borderline_concentration"},
    ]},
    {"id": "doc-18", "product_name": "Trace PFAS Surface Treatment", "manufacturer": "Sensatek Inc",
     "doc_type": "Test Report", "case": "borderline", "components": [
        {"component_name": "Surface Treatment", "substance_name": "Perfluorooctanoic acid (PFOA)", "cas_number": "335-67-1",
         "concentration": 24, "unit": "ppb", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "borderline_concentration"},
    ]},
    {"id": "doc-19", "product_name": "Recycled Plastic Pellet Batch", "manufacturer": "FloorTech Industries",
     "doc_type": "Test Report", "case": "borderline", "components": [
        {"component_name": "Pellet Compound", "substance_name": "Butyl benzyl phthalate (BBP)", "cas_number": "85-68-7",
         "concentration": 0.107, "unit": "pct", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "borderline_concentration"},
    ]},
    {"id": "doc-20", "product_name": "Ceramic Glaze Batch", "manufacturer": "PlayCorp",
     "doc_type": "SDS", "case": "borderline", "components": [
        {"component_name": "Glaze Pigment", "substance_name": "Cadmium", "cas_number": "7440-43-9",
         "concentration": 0.0105, "unit": "pct", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "borderline_concentration"},
    ]},
    {"id": "doc-21", "product_name": "Fabric Softener Concentrate", "manufacturer": "AlpineWear",
     "doc_type": "Test Report", "case": "borderline", "components": [
        {"component_name": "Softener Base", "substance_name": "Perfluorohexanesulfonic acid", "cas_number": "355-46-4",
         "concentration": 26, "unit": "ppb", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "borderline_concentration"},
    ]},

    # --- ambiguous / missing CAS (22-26) ---
    {"id": "doc-22", "product_name": "Proprietary Fluoropolymer Additive", "manufacturer": "ChipProcess Materials",
     "doc_type": "SDS", "case": "ambiguous_missing_cas", "components": [
        {"component_name": "Additive Package", "substance_name": "FluoroMagic XR-9 (proprietary blend)", "cas_number": None,
         "concentration": 2.0, "unit": "pct", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "not_found_in_graph"},
    ]},
    {"id": "doc-23", "product_name": "Generic Metal Finish Coating", "manufacturer": "Acme Coatings Inc",
     "doc_type": "Test Report", "case": "ambiguous_missing_cas", "components": [
        # Deliberately vague: supplier wrote just "Chromate" with no specific compound
        # named. This is a bare substring of many real graph entries (sodium chromate,
        # lead chromate, dichromate, ...) so the fuzzy fallback returns several
        # candidates -- genuinely ambiguous, not a "not found at all" case.
        {"component_name": "Metal Finish", "substance_name": "Chromate", "cas_number": None,
         "concentration": 0.3, "unit": "pct", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "ambiguous_name_match"},
    ]},
    {"id": "doc-24", "product_name": "Budget Extension Cord", "manufacturer": "Voltera Ltd",
     "doc_type": "SDS", "case": "ambiguous_missing_cas", "components": [
        {"component_name": "Cord Sheathing", "substance_name": "Leed (handwritten, likely Lead)", "cas_number": None,
         "concentration": 0.2, "unit": "pct", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "ambiguous_name_match"},
    ]},
    {"id": "doc-25", "product_name": "REACH-Exempt Polymer Coating", "manufacturer": "FloorTech Industries",
     "doc_type": "Test Report", "case": "ambiguous_missing_cas", "components": [
        {"component_name": "Polymer Topcoat", "substance_name": "Next-Gen Non-Fluorinated Repellent Polymer NF-88", "cas_number": None,
         "concentration": 1.0, "unit": "pct", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "not_found_in_graph"},
    ]},
    {"id": "doc-26", "product_name": "Mixed Compliance Multi-Part Assembly", "manufacturer": "Compucase Ltd",
     "doc_type": "Test Report", "case": "ambiguous_missing_cas", "components": [
        {"component_name": "Housing", "substance_name": "Lead", "cas_number": "7439-92-1",
         "concentration": 0.02, "unit": "pct", "expected_status": "COMPLIANT", "expected_reason_code": "within_threshold"},
        {"component_name": "Coating Layer", "substance_name": "Unidentified Fluorosurfactant Blend", "cas_number": None,
         "concentration": 0.8, "unit": "pct", "expected_status": "NEEDS_REVIEW", "expected_reason_code": "not_found_in_graph"},
    ]},
]

styles = getSampleStyleSheet()


def _render_pdf(doc: dict, path: Path) -> None:
    pdf = SimpleDocTemplate(str(path), pagesize=letter,
                             topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    story = [
        Paragraph(f"{doc['doc_type'].upper()}", styles["Heading1"]),
        Paragraph(f"Product: {doc['product_name']}", styles["Normal"]),
        Paragraph(f"Manufacturer: {doc['manufacturer']}", styles["Normal"]),
        Paragraph(f"Document ID: {doc['id']}", styles["Normal"]),
        Spacer(1, 0.25 * inch),
        Paragraph("Section 3: Composition / Information on Ingredients", styles["Heading2"]),
    ]
    table_data = [["Component", "Substance", "CAS Number", "Concentration"]]
    for c in doc["components"]:
        conc_str = f"{c['concentration']}{'%' if c['unit'] == 'pct' else ' ' + c['unit']}"
        table_data.append([c["component_name"], c["substance_name"], c["cas_number"] or "Not listed", conc_str])
    table = Table(table_data, colWidths=[1.6 * inch, 2.6 * inch, 1.2 * inch, 1.2 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph(
        "This document is a synthetic test fixture generated for the SubstanceGuard project "
        "and does not represent a real supplier declaration.", styles["Italic"]))
    pdf.build(story)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ground_truth = {}
    for doc in DOCS:
        pdf_path = OUT_DIR / f"{doc['id']}.pdf"
        _render_pdf(doc, pdf_path)
        ground_truth[doc["id"]] = {
            "product_name": doc["product_name"],
            "manufacturer": doc["manufacturer"],
            "case": doc["case"],
            "components": doc["components"],
        }
    GROUND_TRUTH_PATH.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    print(f"Generated {len(DOCS)} PDFs in {OUT_DIR}")
    print(f"Ground truth written to {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    main()
