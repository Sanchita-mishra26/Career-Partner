from db import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE users MODIFY password_hash VARCHAR(255) NOT NULL;"))
    conn.commit()

print("Schema updated successfully")