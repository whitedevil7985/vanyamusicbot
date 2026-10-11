# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import os
import sys
import json
import time
import asyncio
import signal
import importlib

from anony import (anon, app, config, db, logger,
                   stop, thumb, userbot, yt)
from anony.plugins import all_modules


async def idle():
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
    except NotImplementedError:
        def handler(sig, frame):
            loop.call_soon_threadsafe(stop_event.set)

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    await stop_event.wait()

async def main():
    await db.connect()
    await app.boot()
    await userbot.boot()
    await anon.boot()
    await thumb.start()

    for module in all_modules:
        importlib.import_module(f"anony.plugins.{module}")
    logger.info(f"Loaded {len(all_modules)} modules.")

    if config.COOKIES_URL:
        await yt.save_cookies(config.COOKIES_URL)

    sudoers = await db.get_sudoers()
    app.sudoers.update(sudoers)
    app.bl_users.update(await db.get_blacklisted())
    logger.info(f"Loaded {len(app.sudoers)} sudo users.")

    restart_file = "cache/restart.json"
    if os.path.exists(restart_file):
        try:
            with open(restart_file, "r") as f:
                rdata = json.load(f)
            r_chat = rdata.get("chat_id")
            r_msg = rdata.get("message_id")
            r_time = rdata.get("time", 0)
            elapsed = round(time.time() - r_time, 2)
            if r_chat and r_msg:
                try:
                    await app.edit_message_text(
                        chat_id=r_chat,
                        message_id=r_msg,
                        text=f"✅ <b>Restarted successfully in {elapsed}s!</b>",
                    )
                except Exception as ex:
                    logger.warning(f"Could not edit restart message: {ex}")
            os.remove(restart_file)
        except Exception as ex:
            logger.warning(f"Failed to process restart file: {ex}")

    await idle()
    await stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as ex:
        raise SystemExit(ex)
