import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "test-token")
os.environ.setdefault("WHATSAPP_ACCESS_TOKEN", "test-access-token")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test-phone-number-id")
os.environ.setdefault("BOT_DATABASE_PATH", ":memory:")
