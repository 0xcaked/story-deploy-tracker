# bot.py
import os
import time
import sqlite3
import logging
import requests
from datetime import datetime, timezone
from web3 import Web3, HTTPProvider
from telegram import Bot, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup

# --------------------
# Config
# --------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STORY_RPC = os.getenv("STORY_RPC_URL", "https://mainnet.storyrpc.io")
CHAT_ID = int(os.getenv("ALERT_CHAT_ID", "-1002714144239"))  # your provided chat ID
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "6"))
DB_PATH = os.getenv("DB_PATH", "seen_contracts.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN must be set in env vars")

STORYSCAN_API_BASE = "https://www.storyscan.io/api"
STORYSCAN_UI = "https://www.storyscan.io"
STORY_EXPLORER = "https://explorer.story.foundation"
BLAZING_LINK = "https://t.me/blazing_trading_bot?start=ref_thin-existence-3844"

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

w3 = Web3(HTTPProvider(STORY_RPC))
if not w3.isConnected():
    logger.error("Failed to connect to Story RPC: %s", STORY_RPC)
    raise SystemExit("RPC connection failed")

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# --------------------
# DB
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
    conn.close()

def mark_seen(addr: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO seen_contracts(address, detected_at) VALUES (?, ?)",
        (addr.lower(), int(time.time()))
    )
    conn.commit()
    conn.close()

def is_seen(addr: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT 1 FROM seen_contracts WHERE address = ?", (addr.lower(),)).fetchone()
    conn.close()
    return res is not None

# --------------------
# StoryScan API helpers
# --------------------
def query_sourcecode(contract_address: str):
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": contract_address
    }
    try:
        r = requests.get(STORYSCAN_API_BASE, params=params, timeout=10)
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
    block = w3.eth.get_block(block_num, full_transactions=True)
    for tx in block.transactions:
        if tx.to is None:
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
            bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            mark_seen(contract_addr)

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
