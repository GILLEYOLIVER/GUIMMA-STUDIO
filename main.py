from __future__ import annotations

import sys
from pathlib import Path

# Garante prioridade para imports locais quando o script for executado fora da raiz.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from guimma_app import GuimmaStudioApp


def main() -> int:
    app = GuimmaStudioApp(sys.argv)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
