import subprocess
import hashlib
import json
import base64
import uuid
from datetime import datetime
import os
from fpdf import FPDF
import qrcode
import sqlite3

def store_certificate_to_db(cert_id, end_time, signature, db_file="users.db"):
    """Stores certificate details into the database."""
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    # CORRECTED: Removed redundant CREATE TABLE statement. 
    # The table should only be created by database.py to ensure a single source of truth for the schema.
    c.execute("""
        INSERT INTO certificates (cert_id, end_time, signature)
        VALUES (?, ?, ?)
    """, (cert_id, end_time, signature))
    conn.commit()
    conn.close()

def generate_certificate(log_file="wipe.log", path="X://"):
    PRIVATE_KEY = "signing_key.pem"
    PUBLIC_KEY = "signing_pub.pem"
    CERT_JSON = f"wipe_certificate_{uuid.uuid4().hex}.json"
    CERT_PDF = CERT_JSON.replace(".json", ".pdf")
    QR_FILE = CERT_JSON.replace(".json", "_qr.png")

    # Read log
    with open(log_file, "rb") as f:
        log_data = f.read()

    # SHA-256 hash of log
    log_sha256 = hashlib.sha256(log_data).hexdigest()

    # Sign log using OpenSSL
    sig_file = "wipe.sig"
    subprocess.run([
        "openssl", "dgst", "-sha256",
        "-sign", PRIVATE_KEY,
        "-out", sig_file,
        log_file
    ], check=True)

    with open(sig_file, "rb") as f:
        signature_b64 = base64.b64encode(f.read()).decode()

    # Public key fingerprint
    pubkey_sha256 = subprocess.run(
        ["openssl", "dgst", "-sha256", PUBLIC_KEY],
        capture_output=True, text=True, check=True
    ).stdout.split()[-1]

    # JSON certificate
    certificate = {
        "cert_id": str(uuid.uuid4()),
        "tool_version": "zero_leaks_v0.7",
        "Path": path,
        "start_time": datetime.utcnow().isoformat() + "Z",
        "end_time": datetime.utcnow().isoformat() + "Z",
        "log_sha256": log_sha256,
        "signature": signature_b64,
        "public_key_fingerprint_sha256": pubkey_sha256
    }

    # Save JSON
    with open(CERT_JSON, "w") as f:
        json.dump(certificate, f, indent=4)

    # Store to DB
    store_certificate_to_db(
        certificate["cert_id"],
        certificate["end_time"],
        certificate["signature"]
    )

    # Generate QR code
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(os.path.abspath(CERT_JSON))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(QR_FILE)

    # --- Generate PDF certificate ---
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Zero Leaks Wiping Certificate", ln=True, align="C")
    pdf.ln(10)

    # CORRECTED: Changed the loop to handle long strings (like signatures) gracefully.
    # This prevents the "not enough horizontal space" error.
    for key, value in certificate.items():
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, f"{key}:", ln=True)
        pdf.set_font("Arial", "", 10)
        # Use multi_cell to allow long values to wrap to the next line.
        pdf.multi_cell(0, 5, str(value))
        pdf.ln(2) # Add a small space between entries

    # Fix QR size to fit page width
    page_width = pdf.w - 2 * pdf.l_margin
    qr_width_mm = min(50, page_width)
    x_position = (page_width - qr_width_mm) / 2 + pdf.l_margin
    
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, "Scan QR code to verify JSON certificate:", ln=True)
    pdf.image(QR_FILE, x=x_position, y=pdf.get_y(), w=qr_width_mm)
    pdf.output(CERT_PDF)

    # Clean up temporary files
    os.remove(sig_file)
    os.remove(QR_FILE)

    return CERT_JSON, CERT_PDF

# Standalone run
if __name__ == "__main__":
    # Create a dummy log file for testing
    with open("wipe.log", "w") as f:
        f.write("This is a test log for standalone certificate generation.")
    
    json_file, pdf_file = generate_certificate()
    print(f"Certificate generated: {json_file}, {pdf_file}")