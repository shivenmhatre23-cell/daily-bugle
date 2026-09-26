import os
import sys
import shutil

# Add project root to sys.path so all imports (main, database, trust_engine) resolve cleanly
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Flag serverless environment
os.environ["NETLIFY"] = "true"

# Ensure writable /tmp/bugle.db exists with initial data if bundled
tmp_db = "/tmp/bugle.db"
if not os.path.exists(tmp_db):
    src_db = os.path.join(project_root, "bugle.db")
    if os.path.exists(src_db):
        try:
            shutil.copy2(src_db, tmp_db)
        except Exception as e:
            print(f"[Netlify Functions] Notice copying db to /tmp: {e}")

from mangum import Mangum
from main import app

handler = Mangum(app, lifespan="off")
