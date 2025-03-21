from flask import Flask, request, jsonify, render_template_string
import sqlite3
import time
import os
import re
import requests
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DATABASE = 'faucet.db'
MONAD_AMOUNT = 0.001
TIME_LIMIT = 24 * 60 * 60  # 24 hours

# Load secrets from environment
RECAPTCHA_SECRET = os.getenv('RECAPTCHA_SECRET')
FAUCET_PRIVATE_KEY = os.getenv('PRIVATE_KEY')
MONAD_RPC_URL = os.getenv('MONAD_RPC_URL', 'https://testnet-rpc.monad.xyz')
CHAIN_ID = int(os.getenv('CHAIN_ID', 999))  # Default chain ID; replace if needed

# Web3 setup
w3 = Web3(Web3.HTTPProvider(MONAD_RPC_URL))
FAUCET_ADDRESS = w3.eth.account.privateKeyToAccount(FAUCET_PRIVATE_KEY).address

# HTML form with your reCAPTCHA site key
HTML_FORM = '''
<!DOCTYPE html>
<html>
<head>
    <title>Monad Testnet Faucet</title>
    <script src="https://www.google.com/recaptcha/api.js" async defer></script>
</head>
<body>
    <h2>Monad Testnet Faucet</h2>
    <form action="/faucet" method="post">
        <label for="address">Monad Address:</label><br>
        <input type="text" id="address" name="address" required><br><br>
        <div class="g-recaptcha" data-sitekey="6Lcv-fsqAAAAANv9Z8469ozh9P3vJJzNN24eqPPj"></div><br>
        <input type="submit" value="Request 0.001 MONAD">
    </form>
</body>
</html>
'''

# Initialize the database
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS requests (ip TEXT, address TEXT, timestamp INTEGER)''')
    conn.commit()
    conn.close()

# Get client IP
def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)

# Validate Ethereum address
def is_valid_address(addr):
    return re.match(r'^0x[a-fA-F0-9]{40}$', addr)

# Check rate limit
def can_request(ip):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp FROM requests WHERE ip=? ORDER BY timestamp DESC LIMIT 1", (ip,))
    row = cursor.fetchone()
    conn.close()
    if row:
        last_time = row[0]
        return (int(time.time()) - last_time) > TIME_LIMIT
    return True

# Record request
def record_request(ip, address):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO requests (ip, address, timestamp) VALUES (?, ?, ?)", (ip, address, int(time.time())))
    conn.commit()
    conn.close()

# Verify reCAPTCHA
def verify_recaptcha(token):
    url = 'https://www.google.com/recaptcha/api/siteverify'
    payload = {'secret': RECAPTCHA_SECRET, 'response': token}
    response = requests.post(url, data=payload)
    result = response.json()
    return result.get('success', False)

# Send MONAD tokens
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
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(f"Sent {amount} MONAD to {address}, tx: {tx_hash.hex()}")
        return True
    except Exception as e:
        print(f"Error sending MONAD: {e}")
        return False

@app.route('/', methods=['GET'])
def index():
    return render_template_string(HTML_FORM)

@app.route('/faucet', methods=['POST'])
def faucet():
    address = request.form.get('address')
    recaptcha_token = request.form.get('g-recaptcha-response')
    ip = get_client_ip()

    if not address or not is_valid_address(address):
        return jsonify({'error': 'Invalid address'}), 400

    if not recaptcha_token or not verify_recaptcha(recaptcha_token):
        return jsonify({'error': 'reCAPTCHA failed'}), 400

    if not can_request(ip):
        return jsonify({'error': 'Only 1 request per 24 hrs'}), 429

    if send_monad(address, MONAD_AMOUNT):
        record_request(ip, address)
        return jsonify({'success': f'Sent {MONAD_AMOUNT} MONAD to {address}'}), 200
    else:
        return jsonify({'error': 'Faucet failed'}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
