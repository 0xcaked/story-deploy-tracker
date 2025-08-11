import os
import time
import sqlite3
import logging
import requests
import sys
from datetime import datetime, timezone
from web3 import Web3, HTTPProvider
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import queue
import threading

# Set up logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('story_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --------------------
# Config
# --------------------
TELEGRAM_BOT_TOKEN = "8450398408:AAFcKVmcNRDuvqTpbeigR-p3L8XDvZuEx6s"
STORY_RPC = "https://mainnet.storyrpc.io"
CHAT_ID = "-1002714144239"
POLL_INTERVAL = 6
DB_PATH = "seen_contracts.db"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
DB_CLEANUP_DAYS = 30
DB_POOL_SIZE = 5

# API endpoints and links
STORYSCAN_API_BASE = "https://www.storyscan.io/api"
STORYSCAN_UI = "https://www.storyscan.io"
STORY_EXPLORER = "https://explorer.story.foundation"
BLAZING_LINK = "https://t.me/blazing_trading_bot?start=ref_thin-existence-3844"

# Initialize Web3 and bot
w3 = Web3(HTTPProvider(STORY_RPC))
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# --------------------
# Database
# --------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_contracts (
            address TEXT PRIMARY KEY,
            detected_at INTEGER
        )
    """)
    conn.commit()
    
    cleanup_time = int(time.time()) - (DB_CLEANUP_DAYS * 24 * 60 * 60)
    conn.execute("DELETE FROM seen_contracts WHERE detected_at < ?", (cleanup_time,))
    conn.commit()
    conn.close()

def mark_seen(addr: str):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO seen_contracts(address, detected_at) VALUES (?, ?)",
            (addr.lower(), int(time.time()))
        )
        conn.commit()
    finally:
        conn.close()

def is_seen(addr: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        res = conn.execute(
            "SELECT 1 FROM seen_contracts WHERE address = ?", 
            (addr.lower(),)
        ).fetchone()
        return res is not None
    finally:
        conn.close()

# --------------------
# API Calls
# --------------------
def query_sourcecode(contract_address: str):
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": contract_address
    }
    try:
        r = requests.get(
            STORYSCAN_API_BASE,
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"StoryScan sourcecode query failed for {contract_address}: {e}")
        return None

def query_metadata(contract_address: str):
    try:
        url = f"{STORYSCAN_UI}/api/v2/smart-contracts/{contract_address}"
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.warning(f"Metadata query failed for {contract_address}: {e}")
    return {}

def is_verified(api_resp):
    if not api_resp or "result" not in api_resp:
        return False
    try:
        r = api_resp["result"][0]
        return bool(
            r.get("SourceCode") and r.get("SourceCode").strip() not in ("", "null")
            or r.get("ContractName")
        )
    except Exception:
        return False

# --------------------
# Message Formatting
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
# Contract Processing
# --------------------
def process_block(block_num):
    logger.info(f"Checking block {block_num}")
    try:
        block = w3.eth.get_block(block_num, full_transactions=True)
        for tx in block.transactions:
            if tx.to is None:  # Contract creation transaction
                try:
                    receipt = w3.eth.get_transaction_receipt(tx.hash)
                    contract_addr = receipt.contractAddress
                    if not contract_addr or is_seen(contract_addr):
                        continue

                    logger.info(f"New contract found at {contract_addr}")
                    src_resp = query_sourcecode(contract_addr)
                    if not is_verified(src_resp):
                        logger.info(f"Contract {contract_addr} is not verified")
                        mark_seen(contract_addr)
                        continue

                    logger.info(f"Processing verified contract {contract_addr}")
                    src_meta = src_resp["result"][0]
                    extra_meta = query_metadata(contract_addr)

                    deployer = tx["from"]
                    msg, kb = format_alert(
                        contract_addr, deployer, block_num,
                        block.timestamp, src_meta, extra_meta
                    )

                    # Send alert
                    for attempt in range(MAX_RETRIES):
                        try:
                            bot.send_message(
                                chat_id=CHAT_ID,
                                text=msg,
                                parse_mode='Markdown',
                                reply_markup=kb
                            )
                            logger.info(f"Alert sent for contract {contract_addr}")
                            break
                        except Exception as e:
                            if attempt == MAX_RETRIES - 1:
                                logger.error(f"Failed to send alert for {contract_addr}: {e}")
                            else:
                                time.sleep(1)

                    mark_seen(contract_addr)

                except Exception as e:
                    logger.error(f"Error processing tx {tx.hash}: {e}")
                    continue

    except Exception as e:
        logger.error(f"Error processing block {block_num}: {e}")

# --------------------
# Main Loop
# --------------------
def main():
    logger.info("Starting Story contract monitor...")
    logger.info(f"Using RPC: {STORY_RPC}")
    logger.info(f"Alert chat ID: {CHAT_ID}")
    
    # Check Web3 connection
    try:
        # Test connection by getting the latest block
        w3.eth.block_number
        logger.info("Successfully connected to Story RPC")
    except Exception as e:
        logger.error(f"Failed to connect to Story RPC: {e}")
        return

    logger.info("Connected to Story blockchain")
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return

    # Send startup message
    try:
        bot.send_message(
            chat_id=CHAT_ID,
            text="🚀 Story Contract Monitor Bot Started!"
        )
        logger.info("Sent startup message")
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")

    last_block = w3.eth.block_number
    logger.info(f"Starting from block {last_block}")
    
    while True:
        try:
            latest = w3.eth.block_number
            if latest > last_block:
                for b in range(last_block + 1, latest + 1):
                    process_block(b)
                last_block = latest
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {e}")
