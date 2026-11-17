"""
render_cvs.py
Renderizza i CV sintetici (dataset/synthetic/cvs.json) come file PDF e DOCX
usando più template di layout, per creare un dataset di test realistico
con cui stressare il parser.

Output:
    dataset/synthetic/rendered/<template>/<cv_id>.pdf
    dataset/synthetic/rendered/<template>/<cv_id>.docx
    dataset/synthetic/rendered/manifest.json
        ├── mappa cv_id → {path_pdf, path_docx, template, ground_truth}

Template supportati:
    - classic     : layout single-column con header/sezioni
    - europass    : layout a tabella stile Europass (due colonne)
    - modern      : layout moderno con separatori grafici

Uso (dalla radice del progetto):
    python src/render_cvs.py                # 30 CV, tutti i template
    python src/render_cvs.py --count 100
    python src/render_cvs.py --template classic
    python src/render_cvs.py --formats pdf  # solo PDF
"""

import argparse
import json
import os
import random
from pathlib import Path

# python-docx
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.shared import Inches, Pt, RGBColor

# reportlab per i PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


BASE_DIR = Path(__file__).resolve().parent.parent  # radice progetto (src/ è un livello sotto)
DATASET_DIR = BASE_DIR / "dataset"
SYNTHETIC_DIR = DATASET_DIR / "synthetic"
OUT_DIR = SYNTHETIC_DIR / "rendered"

TEMPLATES = ["classic", "europass", "modern"]


# ─── Loader dei dizionari label ──────────────────────────────────────────────
def load_label_maps() -> dict[str, dict[str, str]]:
    """
    Costruisce mappe id → label per skill, occupations e certificazioni,
    così da poter renderizzare i CV sintetici (che contengono solo ID).
    """
    maps: dict[str, dict[str, str]] = {"skills": {}, "occupations": {}, "certs": {}}

    skills_path = DATASET_DIR / "source" / "skills.json"
    if skills_path.exists():
        with open(skills_path, "r", encoding="utf-8") as f:
            for k, v in json.load(f).items():
                maps["skills"][v.get("id", k)] = v.get("label", "")

    occ_path = DATASET_DIR / "source" / "occupations.json"
    if occ_path.exists():
        with open(occ_path, "r", encoding="utf-8") as f:
            for k, v in json.load(f).items():
                maps["occupations"][v.get("id", k)] = v.get("label", "")

    cert_path = DATASET_DIR / "supplementary" / "certifications.json"
    if cert_path.exists():
        with open(cert_path, "r", encoding="utf-8") as f:
            certs = json.load(f).get("certifications", {})
            for k, v in certs.items():
                maps["certs"][v.get("id", k)] = v.get("label", "")

    return maps


# ─── Normalizzazione del CV in blocchi testuali riutilizzabili ──────────────
def prepare_cv_content(cv_record: dict, label_maps: dict) -> dict:
    """
    Trasforma un record del cvs.json in un dizionario di blocchi
    già stringhificati, pronti per essere piazzati in un template.
    """
    cv = cv_record["cv"]
    persona = cv.get("persona", {})
    education = cv.get("education", {})
    languages = cv.get("languages", [])
    certifications = cv.get("certifications", [])
    skills = cv.get("skills", {})
    work = cv.get("work_experience", [])

    # Contact stub (sintetico, coerente con il nome)
    name = persona.get("name", "Anonymous")
    slug = name.lower().replace(" ", ".")
    contact = {
        "email": f"{slug}@example.com",
        "phone": f"+39 3{random.randint(10, 99)} {random.randint(1000000, 9999999)}",
        "nationality": persona.get("nationality", ""),
    }

    # Summary
    summary = cv.get("raw_text", "").strip()

    # Education
    edu_lines = []
    if education.get("label"):
        edu_line = education["label"]
        if education.get("cycle"):
            edu_line += f" — {education['cycle'].capitalize()}"
        edu_lines.append(edu_line)
        if education.get("area"):
            edu_lines.append(f"Area: {education['area']}")

    # Work experience
    work_lines = []
    for w in work:
        title = w.get("job_title", "").strip()
        company = w.get("company", "").strip()
        country = w.get("country", "").strip()
        years = w.get("years", 0)
        start_year = 2024 - years
        header = f"{title} — {company}"
        if country:
            header += f" ({country})"
        period = f"{start_year} – 2024" if years else "2024"
        work_lines.append({"header": header, "period": period})

    # Skills: risolvi da ID a label
    skill_map = label_maps["skills"]
    essential = [
        skill_map.get(sid, "") for sid in skills.get("essential_ids", [])
    ]
    optional = [skill_map.get(sid, "") for sid in skills.get("optional_ids", [])]
    essential = [s for s in essential if s]
    optional = [s for s in optional if s]

    # Languages
    lang_lines = []
    for l in languages:
        label = l.get("language", "")
        cefr = l.get("cefr", "")
        if label:
            lang_lines.append(f"{label} — {cefr}" if cefr else label)

    # Certifications
    cert_lines = [c.get("label", "") for c in certifications if c.get("label")]

    return {
        "name": name,
        "contact": contact,
        "summary": summary,
        "education": edu_lines,
        "experience": work_lines,
        "skills_essential": essential,
        "skills_optional": optional,
        "languages": lang_lines,
        "certifications": cert_lines,
    }


# ─── Renderer PDF ────────────────────────────────────────────────────────────
def _make_pdf_styles():
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "Name", parent=base["Heading1"], fontSize=20, spaceAfter=4
        ),
        "contact": ParagraphStyle(
            "Contact", parent=base["Normal"], fontSize=9,
            textColor=colors.HexColor("#555555"), spaceAfter=12,
        ),
        "section": ParagraphStyle(
            "Section", parent=base["Heading2"], fontSize=12,
            textColor=colors.HexColor("#1a4a7a"), spaceBefore=12, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontSize=10, leading=14,
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=base["Normal"], fontSize=10, leftIndent=14,
            leading=13,
        ),
    }


def render_pdf(content: dict, template: str, out_path: Path) -> None:
    styles = _make_pdf_styles()
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    story = []

    def section(title: str):
        # Titoli diversi per template → stressa la segmentazione del parser
        variants = {
            "classic": title.upper(),
            "europass": title.capitalize(),
            "modern": f"▸ {title.upper()}",
        }
        story.append(Paragraph(variants.get(template, title), styles["section"]))

    # Header
    story.append(Paragraph(content["name"], styles["name"]))
    c = content["contact"]
    story.append(
        Paragraph(
            f"{c['email']} · {c['phone']} · {c['nationality']}", styles["contact"]
        )
    )

    if content["summary"]:
        section("Profile" if template == "modern" else "Profilo")
        story.append(Paragraph(content["summary"], styles["body"]))

    if content["experience"]:
        labels = {
            "classic": "Esperienza professionale",
            "europass": "Work experience",
            "modern": "Experience",
        }
        section(labels[template])
        for w in content["experience"]:
            story.append(
                Paragraph(f"<b>{w['header']}</b> — {w['period']}", styles["body"])
            )
            story.append(Spacer(1, 4))

    if content["education"]:
        labels = {
            "classic": "Istruzione e formazione",
            "europass": "Education and training",
            "modern": "Education",
        }
        section(labels[template])
        for e in content["education"]:
            story.append(Paragraph(e, styles["body"]))

    if content["skills_essential"] or content["skills_optional"]:
        labels = {
            "classic": "Competenze tecniche",
            "europass": "Skills",
            "modern": "Skills",
        }
        section(labels[template])
        all_skills = content["skills_essential"] + content["skills_optional"]
        # Template "classic" a bullet, gli altri inline con virgola
        if template == "classic":
            for s in all_skills:
                story.append(Paragraph(f"• {s}", styles["bullet"]))
        else:
            story.append(Paragraph(", ".join(all_skills), styles["body"]))

    if content["languages"]:
        labels = {"classic": "Lingue", "europass": "Languages", "modern": "Languages"}
        section(labels[template])
        story.append(Paragraph(" · ".join(content["languages"]), styles["body"]))

    if content["certifications"]:
        labels = {
            "classic": "Certificazioni",
            "europass": "Certifications",
            "modern": "Certifications",
        }
        section(labels[template])
        for c in content["certifications"]:
            story.append(Paragraph(f"• {c}", styles["bullet"]))

    doc.build(story)


# ─── Renderer DOCX ───────────────────────────────────────────────────────────
def _add_heading(doc, text: str, size: int = 13, color=(26, 74, 122)):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(*color)
    return p


def _add_body(doc, text: str, size: int = 10):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(size)
    return p


def render_docx(content: dict, template: str, out_path: Path) -> None:
    doc = Document()

    # Header nome + contatti
    name_p = doc.add_paragraph()
    run = name_p.add_run(content["name"])
    run.bold = True
    run.font.size = Pt(20)

    c = content["contact"]
    contact_p = doc.add_paragraph()
    crun = contact_p.add_run(f"{c['email']} · {c['phone']} · {c['nationality']}")
    crun.font.size = Pt(9)
    crun.font.color.rgb = RGBColor(90, 90, 90)

    def section(title: str):
        variants = {
            "classic": title.upper(),
            "europass": title.capitalize(),
            "modern": f"▸ {title.upper()}",
        }
        _add_heading(doc, variants[template])

    # Europass usa tabelle come fa il vero Europass, gli altri paragrafi normali
    use_table = template == "europass"

    if content["summary"]:
        section("Profilo" if template != "modern" else "Profile")
        _add_body(doc, content["summary"])

    if content["experience"]:
        labels = {
            "classic": "Esperienza professionale",
            "europass": "Work experience",
            "modern": "Experience",
        }
        section(labels[template])
        if use_table:
            tbl = doc.add_table(rows=0, cols=2)
            tbl.autofit = True
            for w in content["experience"]:
                row = tbl.add_row().cells
                row[0].text = w["period"]
                row[1].text = w["header"]
                for cell in row:
                    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        else:
            for w in content["experience"]:
                _add_body(doc, f"{w['header']} — {w['period']}")

    if content["education"]:
        labels = {
            "classic": "Istruzione e formazione",
            "europass": "Education and training",
            "modern": "Education",
        }
        section(labels[template])
        for e in content["education"]:
            _add_body(doc, e)

    if content["skills_essential"] or content["skills_optional"]:
        labels = {
            "classic": "Competenze tecniche",
            "europass": "Skills",
            "modern": "Skills",
        }
        section(labels[template])
        all_skills = content["skills_essential"] + content["skills_optional"]
        if template == "classic":
            for s in all_skills:
                _add_body(doc, f"• {s}")
        else:
            _add_body(doc, ", ".join(all_skills))

    if content["languages"]:
        labels = {"classic": "Lingue", "europass": "Languages", "modern": "Languages"}
        section(labels[template])
        _add_body(doc, " · ".join(content["languages"]))

    if content["certifications"]:
        labels = {
            "classic": "Certificazioni",
            "europass": "Certifications",
            "modern": "Certifications",
        }
        section(labels[template])
        for cert in content["certifications"]:
            _add_body(doc, f"• {cert}")

    doc.save(str(out_path))


# ─── Driver principale ───────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30,
                        help="Numero di CV da renderizzare (default 30)")
    parser.add_argument("--template", choices=TEMPLATES, default=None,
                        help="Renderizza solo il template indicato")
    parser.add_argument("--formats", default="pdf,docx",
                        help="Formati separati da virgola (pdf,docx)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]

    cvs_path = SYNTHETIC_DIR / "cvs.json"
    if not cvs_path.exists():
        print(f"[render_cvs] ERRORE: {cvs_path} non trovato.")
        return

    with open(cvs_path, "r", encoding="utf-8") as f:
        cvs = json.load(f)

    # Campionamento casuale stabile
    sample = random.sample(cvs, min(args.count, len(cvs)))
    label_maps = load_label_maps()

    templates = [args.template] if args.template else TEMPLATES
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for t in templates:
        (OUT_DIR / t).mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, cv_record in enumerate(sample):
        content = prepare_cv_content(cv_record, label_maps)
        cv_id = cv_record.get("cv_id") or f"cv_{i:04d}"
        # Distribuisci i CV sui template a rotazione per bilanciare
        template = templates[i % len(templates)]

        entry = {
            "cv_id": cv_id,
            "template": template,
            "ground_truth": cv_record.get("ground_truth", {}),
        }

        try:
            if "pdf" in formats:
                out_pdf = OUT_DIR / template / f"{cv_id}.pdf"
                render_pdf(content, template, out_pdf)
                entry["path_pdf"] = str(out_pdf.relative_to(BASE_DIR))
            if "docx" in formats:
                out_docx = OUT_DIR / template / f"{cv_id}.docx"
                render_docx(content, template, out_docx)
                entry["path_docx"] = str(out_docx.relative_to(BASE_DIR))
        except Exception as e:
            print(f"[render_cvs] Errore su {cv_id}: {e}")
            continue

        manifest.append(entry)
        if (i + 1) % 10 == 0:
            print(f"[render_cvs] {i + 1}/{len(sample)} renderizzati")

    manifest_path = OUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n[render_cvs] Fatto! {len(manifest)} CV in {OUT_DIR}")
    print(f"[render_cvs] Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
