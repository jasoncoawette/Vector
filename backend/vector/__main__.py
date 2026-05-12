from __future__ import annotations

import uvicorn

from . import logging_setup
from .config import get_settings


def main() -> None:
    # Configure JSON logging BEFORE uvicorn so its startup chatter also
    # uses the same handler (the on_event("startup") hook fires after
    # uvicorn has already emitted "Started server process").
    logging_setup.configure()
    s = get_settings()
    uvicorn.run("vector.app:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":
    main()
