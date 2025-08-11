# bot.py
import os
import time
import sqlite3
import logging
import requests
from datetime import datetime, timezone
from web3 import Web3, HTTPProvider
from telegram import Bot, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from ratelimit import limits, sleep_and_retry
from backoff import on_exception, expo
import queue
import threading

# --------------------
# Config
# --------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

STORY_RPC = os.getenv("STORY_RPC_URL")
if not STORY_RPC:
    raise ValueError("STORY_RPC_URL environment variable is not set")

# Initialize Web3
w3 = Web3(HTTPProvider(STORY_RPC))
# Initialize Telegram bot
bot = Bot(TELEGRAM_BOT_TOKEN)

# Constants
STORYSCAN_API_BASE = "https://storyscan.io/api"

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
CHAT_ID = int(os.getenv("ALERT_CHAT_ID", "-1002714144239"))  # your provided chat ID
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "6"))
DB_PATH = os.getenv("DB_PATH", "seen_contracts.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))  # timeout for HTTP requests
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))  # number of retries for failed requests
DB_CLEANUP_DAYS = int(os.getenv("DB_CLEANUP_DAYS", "30"))  # days to keep records
TELEGRAM_RATE_LIMIT = int(os.getenv("TELEGRAM_RATE_LIMIT", "20"))  # messages per minute
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))  # size of database connection pool

# Configure API endpoints and links
STORYSCAN_API_BASE = "https://www.storyscan.io/api"
STORYSCAN_UI = "https://www.storyscan.io"
STORY_EXPLORER = "https://explorer.story.foundation"
BLAZING_LINK = "https://t.me/blazing_trading_bot?start=ref_thin-existence-3844"

# Set up logging
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# --------------------
# DB
# --------------------
class DBConnectionPool:
    def __init__(self, db_path, pool_size):
        self.db_path = db_path
        self.pool_size = pool_size
        self.connections = queue.Queue(maxsize=pool_size)
        self._init_pool()

    def _init_pool(self):
        for _ in range(self.pool_size):
            conn = sqlite3.connect(self.db_path)
            self.connections.put(conn)

    def get_connection(self):
        return self.connections.get()

    def return_connection(self, conn):
        if not conn:
            return
        try:
            self.connections.put(conn)
        except queue.Full:
            conn.close()

    def close_all(self):
        while not self.connections.empty():
            conn = self.connections.get()
            conn.close()

db_pool = None

def init_db():
    global db_pool
    # Initialize the first connection for setup
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_contracts (
            address TEXT PRIMARY KEY,
            detected_at INTEGER
        )
    """)
    conn.commit()
    
    # Clean up old records
    cleanup_time = int(time.time()) - (DB_CLEANUP_DAYS * 24 * 60 * 60)
    conn.execute("DELETE FROM seen_contracts WHERE detected_at < ?", (cleanup_time,))
    conn.commit()
    conn.close()

    # Initialize the connection pool
    db_pool = DBConnectionPool(DB_PATH, DB_POOL_SIZE)

def mark_seen(addr: str):
    conn = None
    try:
        conn = db_pool.get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO seen_contracts(address, detected_at) VALUES (?, ?)",
            (addr.lower(), int(time.time()))
        )
        conn.commit()
    finally:
        if conn:
            db_pool.return_connection(conn)

def is_seen(addr: str) -> bool:
    conn = None
    try:
        conn = db_pool.get_connection()
        res = conn.execute("SELECT 1 FROM seen_contracts WHERE address = ?", (addr.lower(),)).fetchone()
        return res is not None
    finally:
        if conn:
            db_pool.return_connection(conn)

# --------------------
# StoryScan API helpers
# --------------------
@on_exception(expo, requests.exceptions.RequestException, max_tries=MAX_RETRIES)
@sleep_and_retry
@limits(calls=20, period=60)  # 20 calls per minute
def query_sourcecode(contract_address: str):
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": contract_address
    }
    try:
        r = requests.get(STORYSCAN_API_BASE, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.exception("StoryScan sourcecode query failed: %s", e)
        return None

def query_metadata(contract_address: str):
    # This is the richer Blockscout/StoryScan v2 metadata endpoint
    # Replace with real endpoint if StoryScan docs list one specifically for socials/IP
    try:
        url = f"{STORYSCAN_UI}/api/v2/smart-contracts/{contract_address}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.warning("Metadata query failed: %s", e)
    return {}

def is_verified(api_resp):
    if not api_resp or "result" not in api_resp:
        return False
    try:
        r = api_resp["result"][0]
        if r.get("SourceCode") and r.get("SourceCode").strip() not in ("", "null"):
            return True
        if r.get("ContractName"):
            return True
    except Exception:
        pass
    return False

# --------------------
# Message Sending
# --------------------
@on_exception(expo, requests.exceptions.RequestException, max_tries=MAX_RETRIES)
@sleep_and_retry
@limits(calls=TELEGRAM_RATE_LIMIT, period=60)
def send_telegram_message(msg: str, kb: InlineKeyboardMarkup = None):
    try:
        bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        raise

# --------------------
# Formatting
# --------------------
def format_alert(addr, deployer, block_num, ts_unix, src_meta, extra_meta):
    dt = datetime.fromtimestamp(ts_unix, tz=timezone.utc).astimezone()
    ts = dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    name = src_meta.get("ContractName") or "Unknown"
    compiler = src_meta.get("CompilerVersion", "")
    storyscan_link = f"{STORYSCAN_UI}/address/{addr}/contracts"
    storyexplorer_link = f"{STORY_EXPLORER}/address/{addr}"

    text = [
        "🚀 *New Story Contract Deployed!*",
        f"*Name:* `{name}`",
        f"*Address:* [{addr}]({storyscan_link})",
        f"*Deployer:* `{deployer}`",
        f"*Block:* `{block_num}`",
        f"*Time:* `{ts}`"
    ]
    if compiler:
        text.append(f"*Compiler:* `{compiler}`")

    # Add socials if present
    socials = []
    if extra_meta:
        try:
            links = extra_meta.get("links", {})
            for key in ["website", "twitter", "discord", "telegram"]:
                if key in links and links[key]:
                    socials.append(f"[{key.capitalize()}]({links[key]})")
        except Exception:
            pass
    if socials:
        text.append("*Socials:* " + " | ".join(socials))

    kb = [
        [InlineKeyboardButton("Trade (Blazing)", url=BLAZING_LINK)],
        [InlineKeyboardButton("StoryScan", url=storyscan_link),
         InlineKeyboardButton("Story Explorer", url=storyexplorer_link)]
    ]
    return "\n".join(text), InlineKeyboardMarkup(kb)

# --------------------
# Main loop
# --------------------
def process_block(block_num):
    logger.info("Checking block %d", block_num)
    try:
        block = w3.eth.get_block(block_num, full_transactions=True)
        for tx in block.transactions:
            if tx.to is None:
                try:
                    receipt = w3.eth.get_transaction_receipt(tx.hash)
                    contract_addr = receipt.contractAddress
                    if not contract_addr or is_seen(contract_addr):
                        continue

                    src_resp = query_sourcecode(contract_addr)
                    if not is_verified(src_resp):
                        mark_seen(contract_addr)
                        continue

                    src_meta = src_resp["result"][0]
                    extra_meta = query_metadata(contract_addr)

                    deployer = tx["from"]
                    msg, kb = format_alert(contract_addr, deployer, block_num, block.timestamp, src_meta, extra_meta)
                    send_telegram_message(msg, kb)
                    mark_seen(contract_addr)
                except Exception as e:
                    logger.error(f"Failed to process transaction {tx.hash}: {e}")
                    continue
    except Exception as e:
        logger.error(f"Failed to process block {block_num}: {e}")
        return

def main():
    init_db()
    last_block = w3.eth.block_number
    while True:
        latest = w3.eth.block_number
        if latest > last_block:
            for b in range(last_block + 1, latest + 1):
                process_block(b)
            last_block = latest
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
