from flask import Flask, request, jsonify, render_template_string
import sqlite3
import time
import os
import re
import requests
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DATABASE = 'faucet.db'
MONAD_AMOUNT = 0.001
TIME_LIMIT = 24 * 60 * 60  # 24 hours
FAUCET_DONATION_ADDRESS = "0x28EabC0E86e185E0FEe9ee14E94b1e619429B2B4"

RECAPTCHA_SECRET = os.getenv('RECAPTCHA_SECRET')
FAUCET_PRIVATE_KEY = os.getenv('PRIVATE_KEY')
MONAD_RPC_URL = os.getenv('MONAD_RPC_URL', 'https://testnet-rpc.monad.xyz')
CHAIN_ID = int(os.getenv('CHAIN_ID', 999))

w3 = Web3(Web3.HTTPProvider(MONAD_RPC_URL))
FAUCET_ADDRESS = Account.from_key(FAUCET_PRIVATE_KEY).address

HTML_FORM = '''
<!DOCTYPE html>
<html>
<head>
    <title>Monad Faucet</title>
    <style>
        body {
            background-color: #e6ffe6;
            font-family: Arial, sans-serif;
            text-align: center;
            padding: 50px;
        }
        h1 {
            color: #006600;
        }
        form {
            background-color: #ccffcc;
            padding: 20px;
            border-radius: 10px;
            display: inline-block;
        }
        input[type=text] {
            width: 300px;
            padding: 10px;
            margin: 10px 0;
            border: 1px solid #006600;
            border-radius: 5px;
        }
        input[type=submit] {
            background-color: #009900;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
        input[type=submit]:hover {
            background-color: #007700;
        }
        .donation {
            margin-top: 20px;
            color: #004d00;
            font-size: 14px;
            word-wrap: break-word;
        }
        .recent {
            margin-top: 30px;
            color: #003300;
            font-size: 14px;
        }
        footer {
            margin-top: 50px;
            color: #004d00;
        }
    </style>
    <script src="https://www.google.com/recaptcha/api.js" async defer></script>
</head>
<body>
    <h1>Monad Faucet</h1>
    <form action="/faucet" method="post">
        <label for="address"><strong>Monad Address:</strong></label><br>
        <input type="text" id="address" name="address" required><br><br>
        <div class="g-recaptcha" data-sitekey="6Lfz_vsqAAAAAFm_GR5ahhaMxFHnrQuDHgEC1F2F"></div><br>
        <input type="submit" value="Request 0.001 MONAD">
    </form>
    <div class="donation">
        <p><strong>Support this faucet by donating MONAD!</strong></p>
        <p>Faucet Address:</p>
        <p>{{ faucet_donation_address }}</p>
    </div>
    <div class="recent">
        <h3>Recent Claims</h3>
        {% if recent_claims %}
            <ul>
                {% for addr in recent_claims %}
                    <li>{{ addr }}</li>
                {% endfor %}
            </ul>
        {% else %}
            <p>No recent claims yet.</p>
        {% endif %}
    </div>
    <footer>
        ©Andrenator
    </footer>
</body>
</html>
'''

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS requests (
        ip TEXT, address TEXT, timestamp INTEGER
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS cooldowns (
        ip TEXT PRIMARY KEY, ip_timestamp INTEGER,
        address TEXT UNIQUE, addr_timestamp INTEGER
    )''')
    conn.commit()
    conn.close()

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)

def is_valid_address(addr):
    return re.match(r'^0x[a-fA-F0-9]{40}$', addr)

def can_request(ip, address):
    now = int(time.time())
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT ip_timestamp FROM cooldowns WHERE ip=?", (ip,))
    ip_row = cursor.fetchone()

    cursor.execute("SELECT addr_timestamp FROM cooldowns WHERE address=?", (address,))
    addr_row = cursor.fetchone()
    conn.close()

    if ip_row and now - ip_row[0] < TIME_LIMIT:
        return False
    if addr_row and now - addr_row[0] < TIME_LIMIT:
        return False
    return True

def record_request(ip, address):
    now = int(time.time())
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO requests (ip, address, timestamp) VALUES (?, ?, ?)", (ip, address, now))

    cursor.execute("INSERT OR REPLACE INTO cooldowns (ip, ip_timestamp, address, addr_timestamp) VALUES (?, ?, ?, ?)",
                   (ip, now, address, now))
    conn.commit()
    conn.close()

def get_recent_claims(limit=10):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT address FROM requests ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def verify_recaptcha(token):
    url = 'https://www.google.com/recaptcha/api/siteverify'
    payload = {'secret': RECAPTCHA_SECRET, 'response': token}
    response = requests.post(url, data=payload)
    result = response.json()
    return result.get('success', False)

def send_monad(address, amount):
    try:
        nonce = w3.eth.get_transaction_count(FAUCET_ADDRESS)
        tx = {
            'to': address,
            'value': w3.to_wei(amount, 'ether'),
            'gas': 21000,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
            'chainId': CHAIN_ID
        }
        signed_tx = w3.eth.account.sign_transaction(tx, FAUCET_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return True, f'Transaction sent: {tx_hash.hex()}'
    except Exception as e:
        return False, f"Error sending MONAD: {e}"

@app.route('/', methods=['GET'])
def index():
    recent_claims = get_recent_claims()
    return render_template_string(HTML_FORM, faucet_donation_address=FAUCET_DONATION_ADDRESS, recent_claims=recent_claims)

@app.route('/faucet', methods=['POST'])
def faucet():
    address = request.form.get('address')
    recaptcha_token = request.form.get('g-recaptcha-response')
    ip = get_client_ip()

    if not address or not is_valid_address(address):
        return jsonify({'error': 'Invalid address'}), 400

    if not recaptcha_token or not verify_recaptcha(recaptcha_token):
        return jsonify({'error': 'reCAPTCHA failed'}), 400

    if not can_request(ip, address):
        return jsonify({'error': 'Cooldown active for IP or address (24 hrs)'}), 429

    success, message = send_monad(address, MONAD_AMOUNT)
    if success:
        record_request(ip, address)
        return jsonify({'success': f'Sent {MONAD_AMOUNT} MONAD to {address}'}), 200
    else:
        return jsonify({'error': message}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
