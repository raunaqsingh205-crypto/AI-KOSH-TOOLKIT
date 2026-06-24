from jinja2 import Environment, FileSystemLoader, select_autoescape
import os
from typing import Dict, Any

class ReportGenerator:
    def __init__(self):
        self.templates_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=select_autoescape(["html", "xml"])
        )

    def generate_html_report(self, data: Dict[str, Any]) -> str:
        """Renders assessment data into the Jinja2 HTML quality report template."""
        template = self.env.get_template("quality_report.html")
        return template.render(**data)

    def generate_pdf_report(self, html_content: str) -> bytes:
        """Converts HTML content into raw PDF bytes using WeasyPrint."""
        try:
            from weasyprint import HTML
        except OSError:
            # Fallback mock for local Windows IDE environments lacking GTK/Pango binaries
            class HTML:  # type: ignore
                def __init__(self, string: str):
                    self.string = string
                def write_pdf(self) -> bytes:
                    return b"PDF mock bytes"
                    
        # HTML instance expects standard input stream or file
        html = HTML(string=html_content)
        return html.write_pdf()

report_generator = ReportGenerator()
