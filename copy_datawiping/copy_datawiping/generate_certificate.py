import subprocess, hashlib, json, base64, uuid, os
from datetime import datetime
from fpdf import FPDF
import qrcode
import sqlite3

def store_certificate_to_db(cert_id, end_time, signature, db_file="users.db"):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute("INSERT INTO certificates (cert_id, end_time, signature) VALUES (?, ?, ?)",
              (cert_id, end_time, signature))
    conn.commit()
    conn.close()

def generate_certificate(log_file="wipe.log", path="X://"):
    PRIVATE_KEY, PUBLIC_KEY = "signing_key.pem", "signing_pub.pem"
    if not os.path.exists(PRIVATE_KEY):
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-out", PRIVATE_KEY, "-pkeyopt", "rsa_keygen_bits:2048"])
        subprocess.run(["openssl", "rsa", "-pubout", "-in", PRIVATE_KEY, "-out", PUBLIC_KEY])

    unique_id = uuid.uuid4().hex
    CERT_JSON = f"wipe_certificate_{unique_id}.json"
    CERT_PDF = f"wipe_certificate_{unique_id}.pdf"
    QR_FILE = f"qr_code_{unique_id}.png"
    SIG_FILE = "wipe.sig"

    with open(log_file, "rb") as f: log_data = f.read()
    log_sha256 = hashlib.sha256(log_data).hexdigest()

    subprocess.run(["openssl", "dgst", "-sha256", "-sign", PRIVATE_KEY, "-out", SIG_FILE, log_file], check=True)
    with open(SIG_FILE, "rb") as f: signature_b64 = base64.b64encode(f.read()).decode()

    pubkey_sha256 = subprocess.run(["openssl", "dgst", "-sha256", PUBLIC_KEY], capture_output=True, text=True, check=True).stdout.split()[-1]

    certificate = {
        "cert_id": str(uuid.uuid4()), "tool_version": "1.1_cross_platform", "target_path": path,
        "end_time": datetime.utcnow().isoformat() + "Z", "log_sha256": log_sha256, "signature": signature_b64,
        "public_key_fingerprint_sha256": pubkey_sha256
    }
    
    with open(CERT_JSON, "w") as f: json.dump(certificate, f, indent=4)
    store_certificate_to_db(certificate["cert_id"], certificate["end_time"], certificate["signature"])

    qr = qrcode.make(json.dumps(certificate, indent=2))
    qr.save(QR_FILE)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Zero Leaks Wiping Certificate", ln=True, align="C")
    pdf.ln(10)
    for key, value in certificate.items():
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, f"{key}:", ln=True)
        pdf.set_font("Arial", "", 10)
        pdf.multi_cell(0, 5, str(value))
        pdf.ln(2)
    
    pdf.image(QR_FILE, x=(pdf.w - 50) / 2, w=50)
    pdf.output(CERT_PDF)

    os.remove(SIG_FILE)
    os.remove(QR_FILE)
    return CERT_JSON, CERT_PDF