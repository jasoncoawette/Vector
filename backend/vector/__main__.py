from __future__ import annotations

import uvicorn

from .config import get_settings


def main() -> None:
    s = get_settings()
    uvicorn.run("vector.app:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":
    main()
