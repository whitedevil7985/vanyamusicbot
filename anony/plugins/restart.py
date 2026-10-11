# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import os
import sys
import json
import time
import shutil

from pyrogram import filters, types

from anony import anon, app, db, lang, logger, thumb


@app.on_message(filters.command(["logs"]) & app.sudoers)
@lang.language()
async def _logs(_, m: types.Message):
    sent = await m.reply_text(m.lang["log_fetch"])
    if not os.path.exists("log.txt"):
        return await sent.edit_text(m.lang["log_not_found"])
    await sent.edit_media(
        media=types.InputMediaDocument(
            media="log.txt",
            caption=m.lang["log_sent"].format(app.name),
        )
    )


@app.on_message(filters.command(["logger"]) & app.sudoers)
@lang.language()
async def _logger(_, m: types.Message):
    if len(m.command) < 2:
        return await m.reply_text(m.lang["logger_usage"].format(m.command[0]))
    if m.command[1] not in ("on", "off"):
        return await m.reply_text(m.lang["logger_usage"].format(m.command[0]))

    if m.command[1] == "on":
        await db.set_logger(True)
        await m.reply_text(m.lang["logger_on"])
    else:
        await db.set_logger(False)
        await m.reply_text(m.lang["logger_off"])


@app.on_message(filters.command(["restart"]) & app.sudoers)
@lang.language()
async def _restart(_, m: types.Message):
    sent = await m.reply_text(m.lang["restarting"])

    # Clean cache and downloads directory
    for directory in ["cache", "downloads"]:
        try:
            shutil.rmtree(directory, ignore_errors=True)
            os.makedirs(directory, exist_ok=True)
        except Exception:
            pass

    # Save restart state so bot can edit message after reboot
    try:
        restart_data = {
            "chat_id": m.chat.id,
            "message_id": sent.id,
            "time": time.time(),
        }
        with open("cache/restart.json", "w") as f:
            json.dump(restart_data, f)
    except Exception as err:
        logger.warning(f"Failed to save restart state: {err}")

    try:
        await sent.edit_text(m.lang["restarted"])
    except Exception:
        pass

    # Cleanly stop pytgcalls clients
    for client in getattr(anon, "clients", []):
        try:
            await client.stop()
        except Exception:
            pass

    # Cleanly close database and thumbnail session
    try:
        await db.close()
    except Exception:
        pass

    try:
        await thumb.close()
    except Exception:
        pass

    # Determine correct python executable (prioritise .venv if available)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not project_root or not os.path.exists(os.path.join(project_root, "anony")):
        project_root = os.getcwd()

    venv_python = os.path.join(project_root, ".venv", "bin", "python3")
    if os.path.isfile(venv_python) and os.access(venv_python, os.X_OK):
        python_bin = venv_python
    else:
        python_bin = sys.executable

    os.chdir(project_root)
    os.environ["PYTHONPATH"] = f"{project_root}:{os.environ.get('PYTHONPATH', '')}"

    logger.info("Restarting process via os.execl...")
    os.execl(python_bin, python_bin, "-m", "anony")
