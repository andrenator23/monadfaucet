from flask import Flask, request, jsonify, render_template_string
import sqlite3
import time
import os
import re
import requests
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()  # Load .env variables in Render

app = Flask(__name__)
DATABASE = 'faucet.db'
MONAD_AMOUNT = 0.001
TIME_LIMIT = 24 * 60 * 60  # 24 hrs

# Load secrets from environment
RECAPTCHA_SECRET = os.getenv('RECAPTCHA_SECRET')
FAUCET_PRIVATE_KEY = os.getenv('PRIVATE_KEY')
MONAD_RPC_URL = os.getenv('MONAD_RPC_URL', 'https://testnet-rpc.monad.xyz')  # Default testnet RPC
CHAIN_ID = int(os.getenv('CHAIN_ID', 999))  # Replace with Monad testnet chain ID

# Web3 setup
w3 = Web3(Web3.HTTPProvider(MONAD_RPC_URL))
FAUCET_ADDRESS = w3.eth.account.privateKeyToAccount(FAUCET
