import sqlite3
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        phone_number TEXT NOT NULL
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS certificates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cert_id TEXT NOT NULL UNIQUE,
        end_time TEXT NOT NULL,
        signature TEXT NOT NULL
    )
''')
print("Database 'users.db' initialized successfully.")
conn.commit()
conn.close()