from __future__ import annotations

import sys

from app import GuimmaStudioApp


def main() -> int:
    app = GuimmaStudioApp(sys.argv)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
