import sqlite3

# Connect to the database file (it will be created if it doesn't exist)
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Create the users table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        phone_number TEXT NOT NULL
    )
''')

print("Database 'users.db' and 'users' table initialized successfully.")

# Commit the changes and close the connection
conn.commit()
conn.close()