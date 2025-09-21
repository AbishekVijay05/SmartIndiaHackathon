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

# Create the certificates table to store wipe history
cursor.execute('''
    CREATE TABLE IF NOT EXISTS certificates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        certificate_uuid TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_path TEXT NOT NULL,
        sanitization_standard TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
''')


print("Database 'users.db' with 'users' and 'certificates' tables initialized successfully.")

# Commit the changes and close the connection
conn.commit()
conn.close()
