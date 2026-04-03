import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True, encoding="utf-8")

dsn = os.getenv("DATABASE_URL")
print("ENV_PATH =", ENV_PATH)
print("DATABASE_URL repr =", repr(dsn))
print("DATABASE_URL len =", len(dsn or ""))
