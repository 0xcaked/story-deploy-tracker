import os
import time
import sqlite3
import logging
import asyncio
import sys
from datetime import datetime, timezone
from web3 import Web3, HTTPProvider
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import aiohttp

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
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

# API endpoints and links
STORYSCAN_API_BASE = "https://www.storyscan.io/api"
STORYSCAN_UI = "https://www.storyscan.io"
STORY_EXPLORER = "https://explorer.story.foundation"
BLAZING_LINK = "https://t.me/blazing_trading_bot?start=ref_thin-existence-3844"

# Initialize Web3
w3 = Web3(HTTPProvider(STORY_RPC))

# Initialize bot
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
async def query_sourcecode(session: aiohttp.ClientSession, contract_address: str):
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": contract_address
    }
    try:
        async with session.get(STORYSCAN_API_BASE, params=params) as response:
            response.raise_for_status()
            return await response.json()
    except Exception as e:
        logger.error(f"StoryScan sourcecode query failed for {contract_address}: {e}")
        return None

async def query_metadata(session: aiohttp.ClientSession, contract_address: str):
    try:
        url = f"{STORYSCAN_UI}/api/v2/smart-contracts/{contract_address}"
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
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
async def process_block(session: aiohttp.ClientSession, block_num):
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
                    src_resp = await query_sourcecode(session, contract_addr)
                    if not is_verified(src_resp):
                        logger.info(f"Contract {contract_addr} is not verified")
                        mark_seen(contract_addr)
                        continue

                    logger.info(f"Processing verified contract {contract_addr}")
                    src_meta = src_resp["result"][0]
                    extra_meta = await query_metadata(session, contract_addr)

                    deployer = tx["from"]
                    msg, kb = format_alert(
                        contract_addr, deployer, block_num,
                        block.timestamp, src_meta, extra_meta
                    )

                    # Send alert with retries
                    for _ in range(3):  # Try up to 3 times
                        try:
                            await bot.send_message(
                                chat_id=CHAT_ID,
                                text=msg,
                                parse_mode='Markdown',
                                reply_markup=kb
                            )
                            logger.info(f"Alert sent for contract {contract_addr}")
                            break
                        except Exception as e:
                            logger.error(f"Failed to send alert: {e}")
                            await asyncio.sleep(1)

                    mark_seen(contract_addr)

                except Exception as e:
                    logger.error(f"Error processing tx {tx.hash}: {e}")
                    continue

    except Exception as e:
        logger.error(f"Error processing block {block_num}: {e}")

# --------------------
# Main Loop
# --------------------
async def main():
    logger.info("Starting Story contract monitor...")
    
    # Check Web3 connection
    try:
        # Test connection by getting the latest block
        w3.eth.block_number
        logger.info("Connected to Story blockchain")
    except Exception as e:
        logger.error(f"Failed to connect to Story RPC: {e}")
        return

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return

    # Send startup message
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="🚀 Story Contract Monitor Bot Started!"
        )
        logger.info("Sent startup message")
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")
        # Continue anyway

    last_block = w3.eth.block_number
    logger.info(f"Starting from block {last_block}")
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                latest = w3.eth.block_number
                if latest > last_block:
                    for b in range(last_block + 1, latest + 1):
                        await process_block(session, b)
                    last_block = latest
                await asyncio.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {e}")
        raise
