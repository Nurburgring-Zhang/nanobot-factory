import sqlite3, glob, os
for db in glob.glob(r'D:\Hermes\生产平台\nanobot-factory\backend\data\*.db'):
    try:
        conn = sqlite3.connect(db)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'project%'").fetchall()]
        if tables:
            for t in tables:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
                print(os.path.basename(db), '->', t, ':', cols)
    except Exception as e:
        print(db, 'ERR:', e)
