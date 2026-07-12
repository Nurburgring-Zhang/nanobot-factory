import sqlite3
conn = sqlite3.connect(r'D:\Hermes\生产平台\nanobot-factory\backend\data\imdf_p2.db')
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('all tables:', tables)
