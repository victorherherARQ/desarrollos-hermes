#!/usr/bin/env python3
"""
build_standalone.py — oauth-flow-html skill
Genera un HTML único autocontenido a partir de una spec JSON de flujo OAuth/OIDC.

Uso:
  python3 build_standalone.py --spec examples/flow-c.json --output flow-c.html
  python3 build_standalone.py --spec flow.json                    # → flow.html junto al spec
  python3 build_standalone.py --spec flow.json --embed            # inline styles+scripts (sin archivos sueltos)

El HTML resultante abre con doble clic en cualquier navegador moderno sin servidor.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"


def load_spec(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    spec = json.loads(raw)
    for k in ("title", "actors", "steps"):
        if k not in spec:
            raise ValueError(f"Spec missing required key: {k}")
    actor_ids = {a["id"] for a in spec["actors"]}
    for s in spec["steps"]:
        if s.get("from") not in actor_ids or s.get("to") not in actor_ids:
            raise ValueError(
                f"Step {s.get('n')} references unknown actor: from={s.get('from')} to={s.get('to')}"
            )
    return spec


def main() -> int:
    p = argparse.ArgumentParser(
        description="Generate a standalone HTML OAuth flow diagram from a JSON spec."
    )
    p.add_argument("--spec", required=True, type=Path, help="Path to JSON spec")
    p.add_argument("--output", type=Path, default=None, help="Output .html path (default: alongside spec)")
    p.add_argument("--embed", action="store_true", help="Inline all CSS/JS into a single .html")
    args = p.parse_args()

    spec = load_spec(args.spec)
    output = args.output if args.output else args.spec.with_suffix(".html")
    output.parent.mkdir(parents=True, exist_ok=True)

    # Read templates
    index_html = (ASSETS / "index.template.html").read_text(encoding="utf-8")
    css = (ASSETS / "styles.template.css").read_text(encoding="utf-8")
    render_js = (ASSETS / "render.template.js").read_text(encoding="utf-8")
    app_js = (ASSETS / "app.template.js").read_text(encoding="utf-8")

    # Inject the spec as a JS literal
    flows_literal = json.dumps(spec, ensure_ascii=False)
    html = index_html.replace("__FLOWS_PLACEHOLDER__", flows_literal)
    html = html.replace("__TITLE__", spec.get("title", "OAuth Flow"))

    if args.embed:
        html = html.replace(
            '<link rel="stylesheet" href="./styles.css" />',
            f"<style>\n{css}\n</style>",
        )
        html = html.replace(
            '<script src="./render.js"></script>',
            f"<script>\n{render_js}\n</script>",
        )
        html = html.replace(
            '<script src="./app.js"></script>',
            f"<script>\n{app_js}\n</script>",
        )
        output.write_text(html, encoding="utf-8")
        size_kb = output.stat().st_size / 1024
        print(f"OK (single-file): {output} ({size_kb:.1f} KB)")
        return 0

    # Multi-file build: write index.html + 3 sibling files
    out_dir = output.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / (output.stem + ".html")
    html_path.write_text(html, encoding="utf-8")
    (out_dir / "styles.css").write_text(css, encoding="utf-8")
    (out_dir / "render.js").write_text(render_js, encoding="utf-8")
    (out_dir / "app.js").write_text(app_js, encoding="utf-8")
    print(f"OK (multi-file): {out_dir}/{{*.html, styles.css, render.js, app.js}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())