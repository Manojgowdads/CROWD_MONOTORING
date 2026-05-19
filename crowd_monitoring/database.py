import sqlite3
import pandas as pd
from datetime import datetime
import bcrypt

DB_NAME = "crowd_data.db"

def init_db():
    """Initializes the database tables."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS crowd_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            person_count INTEGER,
            density TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT
        )
    ''')
    conn.commit()
    conn.close()

def register_user(username, password):
    """Registers a new user with a hashed password."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Check if username exists
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    if c.fetchone() is not None:
        conn.close()
        return False
        
    # Hash the password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    
    c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
    conn.commit()
    conn.close()
    return True

def verify_user(username, password):
    """Verifies a user's login credentials."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username=?", (username,))
    result = c.fetchone()
    conn.close()
    
    if result is None:
        return False
        
    stored_hash = result[0]
    return bcrypt.checkpw(password.encode('utf-8'), stored_hash)

def log_data(person_count, density):
    """Logs a single frame's data into the database."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO crowd_logs (person_count, density)
        VALUES (?, ?)
    ''', (person_count, density))
    conn.commit()
    conn.close()

def get_all_data_as_df():
    """Retrieves all logged data as a Pandas DataFrame for export/visualization."""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM crowd_logs ORDER BY timestamp DESC", conn)
    conn.close()
    return df

def get_all_users_as_df():
    """Retrieves all registered users (excluding password hashes for security)."""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT id, username FROM users", conn)
    conn.close()
    return df

def clear_logs():
    """Clears the database logs."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM crowd_logs')
    conn.commit()
    conn.close()

# Initialize on import
init_db()
