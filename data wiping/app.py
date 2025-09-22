import os
import subprocess
import string
import sqlite3
import random
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from generate_certificate import generate_certificate
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Twilio Configuration ---
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

if all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
else:
    print("\n--- TWILIO WARNING ---")
    print("Twilio environment variables not set. OTP via SMS will be disabled.")
    print("OTP will be printed to the console as a fallback.")
    print("----------------------\n")
    twilio_client = None

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

# --- Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("You must be logged in to view this page.", "warning")
            return redirect(url_for('login'))
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
            if session.get('pending_user') == username:
                flash("Please verify your account with OTP before login.", "warning")
                return redirect(url_for('send_otp'))
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['phone_number'] = user['phone_number']
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for('wipe_tool'))
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
        session['pending_user'] = username
        session['phone_number'] = phone_number
        flash("Account created successfully! Please verify with OTP.", "success")
        return redirect(url_for('send_otp'))
    return render_template('signup.html')

@app.route('/send-otp')
def send_otp():
    username = session.get('pending_user')
    if not username:
        flash("OTP not required. Please login.", "info")
        return redirect(url_for('login'))

    otp = str(random.randint(100000, 999999))
    session['otp'] = otp
    phone_number = session.get('phone_number')

    print(f"\n====== OTP FOR {username} IS: {otp} ======\n")

    if twilio_client:
        try:
            twilio_client.messages.create(
                body=f"Your Zero Leaks verification code is: {otp}",
                from_=TWILIO_PHONE_NUMBER,
                to=phone_number
            )
            flash(f"An OTP has been sent to your phone number.", "success")
        except TwilioRestException as e:
            print(f"!!! TWILIO ERROR: {e} !!!")
            flash("Failed to send OTP via SMS. The number may be invalid or not verified.", "danger")
            flash("Please check the server console for the code.", "warning")
    else:
        flash("Twilio is not configured. Please check the server console for the OTP.", "warning")

    return redirect(url_for('verify_otp'))

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        user_otp = request.form['otp']
        if 'otp' in session and session['otp'] == user_otp:
            username = session.get('pending_user')
            if username:
                session.pop('pending_user', None)
                session.pop('otp', None)
                flash("OTP verified successfully! Please login.", "success")
                return redirect(url_for('login'))
        else:
            flash("Invalid OTP. Please try again.", "danger")
    return render_template('verify_otp.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

# --- Wiping Routes ---
@app.route('/wipe-tool')
@login_required
def wipe_tool():
    return render_template('wipe_tool.html')

@app.route('/browse')
@login_required
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
def wipe_file_route():
    data = request.get_json()
    wipe_type = data.get('wipe_type')
    path = data.get('path')
    wipe_method = data.get('wipe_method')
    if not all([wipe_type, path, wipe_method]):
        return jsonify({'stderr': 'ERROR: Missing parameters.'}), 400

    if not os.path.exists(C_EXECUTABLE_PATH):
        return jsonify({'stderr': "Executable not found."}), 500

    command = [C_EXECUTABLE_PATH, f'--{wipe_type}', path, wipe_method]
    process = subprocess.run(command, capture_output=True, text=True)
    log_output = process.stdout + process.stderr

    if process.returncode != 0:
        return jsonify({'stderr': log_output, 'success': False}), 500

    try:
        cert_json, cert_pdf = generate_certificate("wipe.log", path)
    except Exception as e:
        return jsonify({'stderr': f"Certificate generation failed: {str(e)}"}), 500

    return jsonify({
        'log': log_output,
        'success': True,
        'certificate_json': cert_json,
        'certificate_pdf': cert_pdf
    })

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    if os.path.exists(filename):
        return send_file(filename, as_attachment=True)
    flash("File not found!", "danger")
    return redirect(url_for('wipe_tool'))

# --- Main ---
if __name__ == "__main__":
    if not os.path.exists("users.db"):
        print("Database not found! Run 'database.py' first.")
    else:
        app.run(host="0.0.0.0", port=5000, debug=False)