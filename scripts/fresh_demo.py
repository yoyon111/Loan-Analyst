"""Archive the local SQLite demo, then let the next server startup create a fresh one.

Stop both servers first. No PostgreSQL database is modified by this utility.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

root = Path(__file__).resolve().parents[1]
load_dotenv(root / ".env")
url = os.getenv("DATABASE_URL", "sqlite:///./investoffice.db")
if url != "sqlite:///./investoffice.db":
    raise SystemExit(
        "This utility only supports the default local SQLite demo. Use a new database name for PostgreSQL."
    )
source = (root / "investoffice.db").resolve()
if source.parent != root.resolve():
    raise SystemExit("Unexpected database location.")
if not source.exists():
    raise SystemExit("No local demo database exists yet. Start the app to create it.")
backup = root / "backups"
backup.mkdir(exist_ok=True)
destination = backup / (
    "investoffice-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + ".db"
)
source.rename(destination)
print(
    f"Archived all existing demo work to {destination}. Restart the backend for a fresh Harbor case."
)
