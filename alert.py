#!/usr/bin/env python

import logging
import threading
import time
import requests
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# global settings declarations
user_update_rate = 5
data_fetch_rate = 10
data_fetch_url = "https://api.livecoinwatch.com/coins/list"
data_fetch_payload = json.dumps({
    "currency": "USD",
    "sort": "rank",
    "order": "descending",
    "offset": 0,
    "limit": 20000,
    "meta": False
})
data_fetch_headers = {
    "content-type": "application/json",
    "x-api-key": "7d87d695-bc6a-4dfb-80bd-8a2c793ab5a5"
}

# global variable declarations
coin_data = {}
coin_data_keys = []

# enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)


def fetch_data():
    global coin_data, coin_data_keys
    global data_fetch_rate, data_fetch_url, data_fetch_payload, data_fetch_headers

    while True:

        current_time = time.time()
        response = requests.request("POST", data_fetch_url, headers=data_fetch_headers, data=data_fetch_payload).json()
        delta_time = time.time() - current_time

        for coin in response[:]:
            coin_name = coin["code"]
            coin_data[coin_name] = {"rate": coin["rate"],
                                    "volume": coin["volume"],
                                    "cap": coin["cap"],
                                    "time": current_time,
                                    "delta": delta_time}
        coin_data_keys = [*coin_data]

        time.sleep(data_fetch_rate)


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


async def alarm(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the alarm message."""
    global coin_data, coin_data_keys

    job = context.job

    if job.data["coin_name"] in coin_data_keys:
        if job.data["coin_move"] == "up":
            if coin_data[job.data["coin_name"]]["rate"] >= job.data["coin_target"]:
                job.data["handled"] = True
        if job.data["coin_move"] == "down":
            if coin_data[job.data["coin_name"]]["rate"] <= job.data["coin_target"]:
                job.data["handled"] = True

    if job.data["handled"]:
        job.schedule_removal()
        text = f'INFO: {job.data["coin_name"]} {job.data["coin_move"].upper()} reached {job.data["coin_target"]} with {coin_data[job.data["coin_name"]]["rate"]}'
        await context.bot.send_message(job.chat_id, text=text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends explanation on how to use the bot."""
    await update.message.reply_text("USAGE:"
                                    "\n/watch [COIN] [UP/DOWN] [PRICE]"
                                    "\n/unwatch [COIN]"
                                    "\n/check [COIN]"
                                    "\n/help")


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check supported coins."""
    global coin_data, coin_data_keys
    try:
        coin_name = context.args[0]
        if coin_name in coin_data_keys:
            await update.message.reply_text(f'INFO: {coin_name} PRICE: {coin_data[coin_name]["rate"]}')
            return
        elif coin_name.upper() in coin_data_keys:
            await update.message.reply_text(f'WARNING: {coin_name} is supported as {coin_name.upper()}')
            return
        else:
            for coin in coin_data_keys:
                if coin.startswith(coin_name) or coin.endswith(coin_name):
                    await update.message.reply_text(f'WARNING: {coin_name} is supported as {coin}')
                    return
        await update.message.reply_text(f'ERROR: {coin_name} is not supported')
    except Exception as e:
        await update.effective_message.reply_text("USAGE: /check [COIN]")


async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a job to the queue."""
    global user_update_rate, coin_data_keys

    try:

        chat_id = update.effective_message.chat_id

        data = {
            "coin_name": context.args[0],
            "coin_move": context.args[1].lower(),
            "coin_target": float(context.args[2]),
            "handled": False
        }

        if data["coin_name"] not in coin_data_keys:
            await update.effective_message.reply_text(f'ERROR: Coin {data["coin_name"]} not supported')
            return

        if data["coin_move"] not in ("up", "down"):
            await update.effective_message.reply_text("ERROR: Movement should be up or down")
            return

        if float(data["coin_target"]) < 0:
            await update.effective_message.reply_text("ERROR: Price can not be less than zero")
            return

        job_removed = remove_job_if_exists(f'{chat_id}_{data["coin_name"]}', context)
        if job_removed:
            await update.effective_message.reply_text(f'WARNING: Removed old job for {data["coin_name"]}')

        context.job_queue.run_repeating(callback=alarm,
                                        interval=user_update_rate,
                                        chat_id=chat_id,
                                        name=f'{chat_id}_{data["coin_name"]}',
                                        data=data)

        text = f'SUCCESS: Watching {data["coin_name"]} {data["coin_move"]} {data["coin_target"]}'
        await update.effective_message.reply_text(text)

    except Exception as e:
        await update.effective_message.reply_text("USAGE: /watch [COIN] [UP/DOWN] [PRICE]")


async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the job if the user changed their mind."""
    try:
        chat_id = update.message.chat_id
        coin_name = context.args[0]
        job_removed = remove_job_if_exists(f'{chat_id}_{coin_name}', context)
        text = f'SUCCESS: Unwatched {coin_name}' if job_removed else f'ERROR: No job running for {coin_name}'
        await update.effective_message.reply_text(text)
    except Exception as e:
        await update.effective_message.reply_text("USAGE: /unwatch [COIN]")


def main() -> None:
    """Run bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token("5628246260:AAF6W37t3y8GHF4_YAUHh9y_Pv1GLlTYfjU").build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("watch", watch))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CommandHandler("unwatch", unwatch))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    threading.Thread(target=fetch_data).start()
    main()
