"""Atualiza README e fonte do PDF com um link real, informado pelo estudante."""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python scripts/definir_video.py "https://youtu.be/ID"')
    url = sys.argv[1].strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("youtube.com", "www.youtube.com", "youtu.be"):
        raise SystemExit("Informe a URL HTTPS do video publicado no YouTube")
    source = ROOT / "docs/relatorios.json"
    content = json.loads(source.read_text(encoding="utf-8"))
    content["video_url"] = url
    source.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    lines = text.splitlines()
    lines = [f"**Vídeo pitch:** {url}" if line.startswith("**Vídeo pitch:**") else line for line in lines]
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Link atualizado. Gere novamente os PDFs com scripts/gerar_relatorios.py.")


if __name__ == "__main__":
    main()
