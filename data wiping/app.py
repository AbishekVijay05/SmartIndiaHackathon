import os
import subprocess
import string
import sqlite3
import random
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests

app = Flask(__name__)
app.secret_key = os.urandom(24)

C_EXECUTABLE_PATH = os.path.join('wipingEngine', 'wipeEngine.exe')

# --- Helper Functions ---
def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_physical_disks():
    disks = []
    try:
        cmd = "wmic diskdrive get Index,Caption,Size,SerialNumber /format:csv"
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        lines = result.stdout.strip().split('\n')
        for line in lines[2:]:
            if line:
                _, caption, index, serial, size_str = line.strip().split(',')
                size_gb = float(size_str) / (1024**3)
                disk_path = f"\\\\.\\PhysicalDrive{index}"
                display_name = f"Disk {index}: {caption.strip()} (SN: {serial.strip()}) ({size_gb:.2f} GB)"
                disks.append({'path': disk_path, 'name': display_name, 'serial': serial.strip()})
    except Exception as e:
        print(f"Could not get physical disks: {e}")
    return disks

# --- Decorators for Route Protection ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("You must be logged in to view this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def otp_verified_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('otp_verified'):
            flash("Please verify your identity with an OTP.", "warning")
            return redirect(url_for('verify_otp'))
        return f(*args, **kwargs)
    return decorated_function

# --- Authentication Routes ---
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('wipe_tool'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['phone_number'] = user['phone_number']
            session['otp_verified'] = False
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for('verify_otp'))
        else:
            flash("Invalid username or password.", "danger")
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        phone_number = request.form['phone_number']
        conn = get_db_connection()
        user_exists = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if user_exists:
            flash("Username already exists. Please choose another.", "warning")
            conn.close()
            return redirect(url_for('signup'))
        password_hash = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, password_hash, phone_number) VALUES (?, ?, ?)',
                     (username, password_hash, phone_number))
        conn.commit()
        conn.close()
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
@login_required
def verify_otp():
    if request.method == 'POST':
        user_otp = request.form['otp']
        if 'otp' in session and session['otp'] == user_otp:
            session['otp_verified'] = True
            session.pop('otp', None)
            flash("Verification successful! Access granted.", "success")
            return redirect(url_for('wipe_tool'))
        else:
            flash("Invalid OTP. Please try again.", "danger")
    return render_template('verify_otp.html')

@app.route('/send-otp')
@login_required
def send_otp():
    otp = str(random.randint(100000, 999999))
    session['otp'] = otp
    phone_number = session.get('phone_number', 'N/A')
    whaNum = "91"+phone_number
    url = "https://graph.facebook.com/v22.0/753864777817921/messages"
    headers = {
    "Authorization": "Bearer EAALC3e2CyZBYBPb3rWXyPkr2kNvr7307NA4cNCLIQrOXji2bovgSuZBuvFBzsreOlZBeK0kZBe3QZAiv1mLlLEe6iVvZBZBRPBevxzcI8JfSNixuZAp5TfhoRalZAnI5UotMBxNdbSOVmkN4emkSOfEnTckKbhGVEh3sBuWByuZCYYjwCkm4g60UFjV7iWN6BHmHHFKSjVP6LkP593x2UCZCxZC0eZBZCTTFreLJ8m1Aee8luIvxi9SQZDZD ",
    "Content-Type": "application/json"
    }
    payload = {
    "messaging_product": "whatsapp",
    "to": whaNum,
    "type": "template",
    "template": {
      "name": "hello_world",
      "language": { "code": "en_US" }
    }
    }

    response = requests.post(url, headers=headers, json=payload)
    print(response.json())

    print("\n" + "="*50)
    print(f"      OTP FOR USER: {session.get('username')}")
    print(f"      PHONE NUMBER: {phone_number}")
    print(f"      YOUR OTP IS: {otp}")
    print("="*50 + "\n")
    flash(f"An OTP has been sent to the console.", "info")
    return redirect(url_for('verify_otp'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

# --- Main Application Routes ---
@app.route('/wipe-tool')
@login_required
@otp_verified_required
def wipe_tool():
    return render_template('wipe_tool.html')

@app.route('/browse')
@login_required
@otp_verified_required
def browse_fs():
    wipe_type = request.args.get('type', 'file')
    if wipe_type == 'disk':
        disks = get_physical_disks()
        return jsonify({'disks': disks})
    path = request.args.get('path', None)
    drives = [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]
    allowed_roots = [os.path.abspath(d) for d in drives]
    if not path:
        return jsonify({'current_path': '', 'folders': allowed_roots, 'files': []})
    requested_path = os.path.abspath(path)
    if not any(requested_path.startswith(root) for root in allowed_roots):
        return jsonify({"error": "Access denied."}), 403
    try:
        items = os.listdir(requested_path)
        folders = sorted([item for item in items if os.path.isdir(os.path.join(requested_path, item))])
        files = sorted([item for item in items if not os.path.isdir(os.path.join(requested_path, item))])
        parent_path = os.path.dirname(requested_path)
        if requested_path.rstrip('\\') in allowed_roots: parent_path = ''
        return jsonify({'current_path': requested_path, 'parent_path': parent_path, 'folders': folders, 'files': files})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/wipe', methods=['POST'])
@login_required
@otp_verified_required
def wipe_file_route():
    data = request.get_json()
    wipe_type = data.get('wipe_type')
    path = data.get('path')
    wipe_method = data.get('wipe_method')
    if not all([wipe_type, path, wipe_method]):
        return jsonify({'stderr': 'ERROR: Missing parameters.'}), 400
    if not os.path.exists(C_EXECUTABLE_PATH):
        return jsonify({'stderr': f"ERROR: Executable not found. Please compile the C code."}), 500
    try:
        command = [C_EXECUTABLE_PATH, f'--{wipe_type}', path, wipe_method]
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        log_output = process.stdout + process.stderr
        return jsonify({'log': log_output, 'success': process.returncode == 0})
    except Exception as e:
        return jsonify({'stderr': f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    if not os.path.exists('users.db'):
        print("ERROR: Database 'users.db' not found!")
        print("Please run 'python database.py' once to create it.")
    else:
        print("Starting Zero Leaks server...")
        print("Access the tool at http://127.0.0.1:5000")
        app.run(host='0.0.0.0', port=5000, debug=False)