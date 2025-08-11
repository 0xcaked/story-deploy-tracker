[README.md](https://github.com/user-attachments/files/21709119/README.md)
# Story Contract Monitor Bot

A Telegram bot that monitors the Story blockchain for new contract deployments and sends notifications when verified contracts are detected.

## Features

- Monitors new blocks on Story blockchain in real-time
- Detects contract creation transactions
- Checks if contracts are verified on StoryScan
- Sends formatted notifications to Telegram with:
  - Contract name and address
  - Deployer address
  - Deployment time and block number
  - Compiler version
  - Links to StoryScan and Story Explorer
  - Social media links when available
  - Quick link to trade on Blazing DEX

## Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure environment variables (or edit them directly in bot.py):
   - TELEGRAM_BOT_TOKEN
   - STORY_RPC
   - CHAT_ID

## Running

```bash
python src/bot.py
```

The bot will create required directories (logs/, data/) on first run.

## Deployment

The project includes a Procfile for deployment on Railway or similar platforms.

## Structure

```
story-contract-bot/
├── src/
│   └── bot.py
├── data/
│   └── seen_contracts.db
├── logs/
│   └── bot.log
├── requirements.txt
├── Procfile
└── README.md
```

## Dependencies

- python-telegram-bot
- web3
- aiohttp

## License

MIT
