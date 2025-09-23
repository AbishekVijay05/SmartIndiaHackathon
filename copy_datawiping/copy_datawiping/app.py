import os
import subprocess
import string
import sqlite3
import random
import sys
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from generate_certificate import generate_certificate
import requests

url = "https://graph.facebook.com/v22.0/753864777817921/messages"
headers = {
    "Authorization": "Bearer <AccesTocken>",
    "Content-Type": "application/json"
}

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Cross-Platform Executable Path ---
if sys.platform == "win32":
    executable_name = "wipeEngine.exe"
else:
    executable_name = "wipeEngine"
C_EXECUTABLE_PATH = os.path.join('wipingEngine', executable_name)

# --- Helper Functions ---
def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_physical_disks():
    disks = []
    try:
        if sys.platform == "win32":
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
        else:
            # On Linux, this may need to be run with sudo to get all details
            cmd = ["lsblk", "-d", "-o", "NAME,MODEL,SIZE,SERIAL", "--bytes", "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            for disk in data.get('blockdevices', []):
                disk_path = os.path.join('/dev', disk.get('name', ''))
                model = disk.get('model', 'N/A')
                size_gb = float(disk.get('size', 0)) / (1024**3)
                serial = disk.get('serial', 'N/A')
                display_name = f"{disk_path}: {model} (SN: {serial}) ({size_gb:.2f} GB)"
                disks.append({'path': disk_path, 'name': display_name, 'serial': serial})
    except Exception as e:
        print(f"Could not get physical disks (do you need to run as admin/sudo?): {e}")
    return disks

# --- Decorators & Authentication ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("You must be logged in to view this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    # Always show the landing page first
    return render_template('landing.html')   # <-- new UI file

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

whanum = "91" 
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        phone_number = request.form['phone_number']
        #print(type(phone_number))
        global whanum
        whanum += phone_number
        print(whanum)
        print(type(whanum))
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
    otp = str(otp)
    
    payload = {
        "messaging_product": "whatsapp",
        "to": whanum,
        "type": "template",
        "template": {
            "name": "otp_verification",
            "language": { "code": "en" },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": otp
                        }
                    ]
                },
                {
                    "type": "button",
                    "sub_type": "url",  # ✅ for “Copy code” style buttons
                    "index": 0,
                    "parameters": [
                        {
                            "type": "payload",
                            "payload": "copy_code"  # can be any identifier for your app logic
                        }
                    ]
                }
            ]
        }
    }
    print(f"\n====== OTP FOR {username} IS: {otp} ======\n")
    response = requests.post(url, headers=headers, json=payload)
    flash("OTP sent to console! Please verify.", "info")
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
@login_required
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
        return jsonify({'disks': get_physical_disks()})
    path = request.args.get('path', None)
    if not path:
        if sys.platform == "win32":
            drives = [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]
        else:
            drives = ['/']
        return jsonify({'current_path': '', 'folders': drives, 'files': []})
    try:
        requested_path = os.path.abspath(path)
        items = os.listdir(requested_path)
        folders = sorted([item for item in items if os.path.isdir(os.path.join(requested_path, item))])
        files = sorted([item for item in items if not os.path.isdir(os.path.join(requested_path, item))])
        parent_path = os.path.dirname(requested_path)
        if sys.platform != "win32" and parent_path == requested_path:
            parent_path = ''
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
        return jsonify({'stderr': f"Executable not found at {C_EXECUTABLE_PATH}. Please compile it for your system."}), 500
    command = [C_EXECUTABLE_PATH, f'--{wipe_type}', path, wipe_method]
    process = subprocess.run(command, capture_output=True, text=True)
    log_output = process.stdout + process.stderr
    with open("wipe.log", "w") as f:
        f.write(log_output)
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

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/api/chatbot', methods=['POST'])
def chatbot_api():
    """Handle chatbot messages and return responses"""
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({
                'error': 'No message provided'
            }), 400
        
        user_message = data['message'].strip()
        
        if not user_message:
            return jsonify({
                'error': 'Empty message'
            }), 400
        
        # Generate bot response based on keywords
        bot_response = get_chatbot_response(user_message)
        
        return jsonify({
            'response': bot_response,
            'timestamp': str(random.randint(100000, 999999))  # Simple timestamp
        })
        
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@app.route('/api/chatbot/suggestions', methods=['GET'])
def chatbot_suggestions():
    """Return suggested questions for the chatbot"""
    suggestions = [
        "How secure is your data wiping process?",
        "What methods do you use for data destruction?",
        "Do you have security certifications?",
        "How long does the process take?",
        "What are your pricing options?",
        "How can I get support?"
    ]
    
    return jsonify({
        'suggestions': suggestions
    })

def get_chatbot_response(user_message):
    """Generate chatbot response based on user message"""
    user_message = user_message.lower().strip()
    
    # Check for keywords and return appropriate response
    if any(word in user_message for word in ['safe', 'secure', 'security', 'protection']):
        return "CRABEX uses military-grade encryption and secure deletion algorithms to ensure your data is completely destroyed following DoD 5220.22-M standards."
    elif any(word in user_message for word in ['how', 'method', 'process', 'work']):
        return "We use multiple overwriting passes with random data patterns and support various storage types including HDDs, SSDs, mobile devices, and cloud storage."
    elif any(word in user_message for word in ['certificate', 'certified', 'compliance', 'standard']):
        return "CRABEX is certified under ISO 27001 and SOC 2 Type II compliance standards, maintaining NIST cybersecurity framework compliance."
    elif any(word in user_message for word in ['support', 'help', 'contact', 'assistance']):
        return "Our support team is available 24/7 to assist with any questions. You can reach us through the contact form, email, or live chat."
    elif any(word in user_message for word in ['price', 'cost', 'pricing', 'fee', 'charge']):
        return "Our pricing is based on the type and amount of data to be destroyed. We offer competitive rates with no hidden fees. Contact us for a free quote."
    elif any(word in user_message for word in ['time', 'long', 'duration', 'fast', 'quick']):
        return "Most data wiping jobs are completed within 24-48 hours. Emergency services are available for urgent requests with real-time updates."
    elif any(word in user_message for word in ['hello', 'hi', 'hey', 'greetings']):
        return "Hello! I'm here to help you with any questions about CRABEX data wiping services. What would you like to know?"
    elif any(word in user_message for word in ['thank', 'thanks']):
        return "You're welcome! Is there anything else I can help you with regarding our data wiping services?"
    else:
        return "I'd be happy to help you with information about our data wiping services, security measures, pricing, or support options. Could you please be more specific?"

# --- Main ---
if __name__ == "__main__":
    if not os.path.exists("users.db"):
        print("Database not found! Run 'database.py' first.")
    else:
        app.run(host="0.0.0.0", port=5000, debug=False)
