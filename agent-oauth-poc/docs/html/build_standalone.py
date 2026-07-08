#!/usr/bin/env python3
"""
build_standalone.py — genera flowstudio.html (HTML único autocontenido)
                      a partir de index.html + static/.

Uso:
  python3 build_standalone.py
  # → crea docs/html/flowstudio.html

Eso permite abrir el HTML con doble clic en el explorador sin necesidad de
servidor local (los ES modules están inline como blobs `application/javascript`).
"""

import base64
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX_HTML = HERE / "index.html"
STATIC_DIR = HERE / "static"
OUTPUT     = HERE / "flowstudio.html"


def minify_inline_css(css: str) -> str:
    """Compresión muy básica de CSS."""
    # Quitar comentarios
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    # Quitar espacios múltiples y saltos
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};:,>+])\s*", r"\1", css)
    css = css.strip()
    return css


def main() -> int:
    if not INDEX_HTML.exists():
        print(f"[ERROR] No se encuentra {INDEX_HTML}")
        return 1
    for n in ("styles.css", "flows.js", "render.js", "app.js"):
        if not (STATIC_DIR / n).exists():
            print(f"[ERROR] Falta {STATIC_DIR / n}")
            return 1

    # 1) Leer HTML
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 2) Leer fuentes
    css_raw   = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    flows_js  = (STATIC_DIR / "flows.js").read_text(encoding="utf-8")
    render_js = (STATIC_DIR / "render.js").read_text(encoding="utf-8")
    app_js    = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    # 3) En JS, los imports "./flows.js" y "./render.js" desaparecen al volverse inline.
    #    Re-escribimos para no usar imports (todo en mismo scope).
    #    flows.js y render.js usan `export`. Hay que quitar `export` y consolidar
    #    en un único IIFE que devuelva { FLOWS, renderFlow, applyState, getFlowActorIds }.
    #    app.js hace `import { FLOWS } from './flows.js'; import { renderFlow, applyState, getFlowActorIds } from './render.js';`
    #    Lo dejamos como: import desde un namespace global `M`.
    flows_inline = re.sub(r"^export\s+", "", flows_js, flags=re.MULTILINE)
    render_inline = re.sub(r"^export\s+", "", render_js, flags=re.MULTILINE)

    # ⚠️ Salvaguarda: cualquier "</script>" literal dentro de un template-string
    # cerraría el <script> del bundle prematuramente. Lo escapamos.
    def safe_for_inline(js: str) -> str:
        return js.replace("</script>", "<\\/script>")

    flows_inline  = safe_for_inline(flows_inline)
    render_inline = safe_for_inline(render_inline)

    # 4) Concatenar con un namespace compartido
    # NOTA: usamos concatenación en vez de f-string porque los JS fuente
    # contienen { y } que romperían el f-string (se interpretarían como
    # placeholders de variables). La triple-comilla de f-string NO escapa
    # automáticamente esos caracteres.
    bundled_js = (
        "(function() {\n"
        "  const M = {};\n"
        + flows_inline + "\n"
        + render_inline + "\n"
        "  const M2 = {\n"
        "    FLOWS,\n"
        "    renderFlow,\n"
        "    applyState,\n"
        "    getFlowActorIds,\n"
        "  };\n"
        "  window.FLOWSTUDIO = M2;\n"
        "})();\n"
        + app_js.replace("import { FLOWS } from './flows.js';",
                         "const { FLOWS } = window.FLOWSTUDIO;")
                .replace("import { renderFlow, applyState, getFlowActorIds } from './render.js';",
                         "const { renderFlow, applyState, getFlowActorIds } = window.FLOWSTUDIO;")
    )
    css_inline = minify_inline_css(css_raw)

    # 5) Reemplazar referencias en HTML:
    #    - <link rel="stylesheet" href="static/styles.css"> → <style>...</style>
    #    - <script type="module" src="static/flows.js"></script> → vacío
    #    - <script type="module" src="static/render.js"></script> → vacío
    #    - <script type="module" src="static/app.js"></script> → <script>...bundle...</script>
    html = re.sub(
        r'<link rel="stylesheet"[^>]*href="(?:\./)?static/styles\.css"[^>]*/?>',
        lambda _m: f"<style>{css_inline}</style>",
        html,
    )

    # Borrar los 3 module scripts y añadir uno solo (el bundle, no-module).
    bundle_script = f"<script>\n{bundled_js}\n</script>"
    html = re.sub(
        r'<script type="module" src="(?:\./)?static/flows\.js"></script>\s*'
        r'<script type="module" src="(?:\./)?static/render\.js"></script>\s*'
        r'<script type="module" src="(?:\./)?static/app\.js"></script>',
        lambda _m: bundle_script,
        html,
    )

    # 6) Añadir banner al inicio del HTML
    banner = (
        "<!--\n"
        "  flowstudio.html — versión standalone generada por build_standalone.py.\n"
        "  Doble-clic para abrir; no necesita servidor.\n"
        "  Fuente: docs/html/{index.html,static/} — para editar, modifica esos\n"
        "  ficheros y vuelve a ejecutar build_standalone.py.\n"
        "-->\n"
    )
    html = banner + html

    # 7) Escribir
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"[OK] Generado {OUTPUT}  ({len(html):,} bytes)")
    print(f"     Tamaño fuente: CSS={len(css_raw):,}  JS={len(flows_js)+len(render_js)+len(app_js):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())