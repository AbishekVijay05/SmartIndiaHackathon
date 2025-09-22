import sqlite3

# Connect to the database file (it will be created if it doesn't exist)
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Create the users table
# Added UNIQUE constraints to username and phone_number to prevent duplicates
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        phone_number TEXT NOT NULL UNIQUE
    )
''')

# Modify certificates table to store cert_id, end_time, and signature
cursor.execute('''
    CREATE TABLE IF NOT EXISTS certificates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cert_id TEXT NOT NULL UNIQUE,
        end_time TEXT NOT NULL,
        signature TEXT NOT NULL
    )
''')

print("Database 'users.db' with 'users' and modified 'certificates' table initialized successfully.")

# Commit the changes and close the connection
conn.commit()
conn.close()
