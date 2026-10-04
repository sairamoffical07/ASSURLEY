import re

with open('backend/app/main.py', 'r', encoding='utf-8') as f:
    code = f.read()

new_db_url = '''if os.getenv("VERCEL"):
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/assurley.db")
    UPLOAD_DIR = Path("/tmp/uploads")
else:
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{APP_DIR / 'data' / 'assurley.db'}")
    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", APP_DIR / "data" / "uploads"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
'''

code = re.sub(
    r'UPLOAD_DIR = Path\(os\.getenv\("UPLOAD_DIR".*?DATABASE_URL = os\.getenv\("DATABASE_URL".*?\)',
    new_db_url,
    code,
    flags=re.DOTALL
)

with open('backend/app/main.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Updated main.py for Vercel")
