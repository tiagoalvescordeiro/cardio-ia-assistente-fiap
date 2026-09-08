"""Gera docs/relatorio_genai.pdf a partir de docs/relatorio_genai.md (Ir Além 1)."""
from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "docs" / "relatorio_genai.md"
PDF_PATH = ROOT / "docs" / "relatorio_genai.pdf"


class PDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(self.family_name, size=8)
        self.set_text_color(100, 100, 100)
        self.cell(
            0,
            8,
            f"CardioIA — Ir Além 1 | Página {self.page_no()}/{{nb}} | "
            "Não é dispositivo médico · 192 SAMU",
            align="C",
        )


def strip_md_inline(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return s.strip()


def resolve_font() -> tuple[str, Path, Path]:
    import fpdf

    fpdf_dir = Path(fpdf.__file__).parent
    regular = next(fpdf_dir.rglob("DejaVuSans.ttf"), None)
    bold = next(fpdf_dir.rglob("DejaVuSans-Bold.ttf"), None)
    if regular is not None:
        return "DejaVu", regular, bold or regular
    arial = Path(r"C:\Windows\Fonts\arial.ttf")
    arialbd = Path(r"C:\Windows\Fonts\arialbd.ttf")
    if arial.exists():
        return "ArialUni", arial, arialbd if arialbd.exists() else arial
    raise SystemExit("Nenhuma fonte Unicode encontrada (DejaVu/Arial).")


def main() -> None:
    text = MD_PATH.read_text(encoding="utf-8")
    family, regular, bold = resolve_font()

    pdf = PDF(format="A4")
    pdf.family_name = family
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font(family, "", str(regular))
    pdf.add_font(family, "B", str(bold))
    pdf.add_page()
    pdf.set_margins(18, 16, 18)

    in_code = False
    code_buf: list[str] = []

    def flush_code() -> None:
        nonlocal code_buf
        if not code_buf:
            return
        pdf.set_font(family, size=8)
        pdf.set_fill_color(245, 245, 245)
        pdf.multi_cell(0, 4.2, "\n".join(code_buf), fill=True)
        pdf.ln(2)
        code_buf = []

    def write_para(s: str, size: int = 10, style: str = "") -> None:
        pdf.set_font(family, style=style, size=size)
        pdf.set_text_color(20, 20, 20)
        cleaned = strip_md_inline(s)
        if not cleaned:
            return
        pdf.multi_cell(0, 5.2, cleaned)
        pdf.ln(1)

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_code()
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        if not line.strip():
            pdf.ln(1.5)
            continue
        if line.startswith("# "):
            write_para(line[2:], size=16, style="B")
            pdf.ln(1)
        elif line.startswith("## "):
            write_para(line[3:], size=13, style="B")
        elif line.startswith("### "):
            write_para(line[4:], size=11, style="B")
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            write_para(" · ".join(cells), size=9)
        elif line.startswith("- "):
            write_para("• " + line[2:], size=10)
        else:
            write_para(line, size=10)

    flush_code()
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(PDF_PATH))
    print(f"OK: {PDF_PATH} ({PDF_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
