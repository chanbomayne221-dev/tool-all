"""DUYỆT NẠP – auto bấm nút "✅ Duyệt" trong tin nhắn của bot nạp tiền.

Cách hoạt động:
- Mở session telethon đã chọn.
- Lắng nghe NewMessage + MessageEdited từ đúng bot_username.
- Khi text chứa trigger (mặc định "YÊU CẦU NẠP TIỀN") -> chờ `delay` giây,
  refetch message, tìm inline button có chữ "Duyệt" và bấm.
- Chạy tới khi stop_event được set.
"""
import asyncio
from telethon import events
from telethon.errors import FloodWaitError
from .session_mgr import make_client


async def _click_duyet(client, msg, button_text, log, tag):
    fresh = await client.get_messages(msg.chat_id, ids=msg.id)
    if fresh is None:
        await log(f"[{tag}] ⚠ Tin đã bị xoá, bỏ qua msg_id={msg.id}")
        return
    if not fresh.buttons:
        await log(f"[{tag}] ⚠ Tin không có nút bấm (msg_id={fresh.id})")
        return
    for row in fresh.buttons:
        for btn in row:
            if button_text.lower() in (btn.text or "").lower():
                try:
                    res = await btn.click()
                    await log(f"[{tag}] ✅ Đã bấm '{btn.text}' (msg_id={fresh.id})")
                    return res
                except FloodWaitError as e:
                    await log(f"[{tag}] ⏳ FloodWait {e.seconds}s khi bấm nút")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    await log(f"[{tag}] ❌ Lỗi bấm nút: {e}")
                    return
    await log(f"[{tag}] ⚠ Không tìm thấy nút chứa '{button_text}' (msg_id={fresh.id})")


async def run_duyet(session_name, bot_username, delay, trigger, button_text,
                    stop_event, log):
    tag = session_name
    client = make_client(session_name)
    pending: set[asyncio.Task] = set()
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await log(f"[{tag}] ❌ Session die")
            return

        # Resolve bot entity 1 lần
        bot_uname = bot_username.lstrip("@")
        try:
            bot_entity = await client.get_entity(bot_uname)
            bot_id = bot_entity.id
        except Exception as e:
            await log(f"[{tag}] ❌ Không tìm thấy bot @{bot_uname}: {e}")
            return

        await log(f"[{tag}] 🚀 DUYỆT NẠP đang chạy")
        await log(f"[{tag}] 👀 Bot: @{bot_uname} | trigger='{trigger}' | "
                  f"delay={delay}s | button='{button_text}'")

        async def schedule(msg):
            await log(f"[{tag}] ⏳ Phát hiện lệnh nạp (msg_id={msg.id}), "
                      f"chờ {delay}s rồi bấm Duyệt…")
            try:
                await asyncio.sleep(delay)
                if stop_event.is_set():
                    return
                await _click_duyet(client, msg, button_text, log, tag)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                await log(f"[{tag}] ❌ {e}")

        @client.on(events.NewMessage(from_users=bot_id))
        @client.on(events.MessageEdited(from_users=bot_id))
        async def _handler(event):
            try:
                text = event.message.message or ""
                if trigger.lower() not in text.lower():
                    return
                t = asyncio.create_task(schedule(event.message))
                pending.add(t)
                t.add_done_callback(pending.discard)
            except Exception as e:
                await log(f"[{tag}] ❌ handler: {e}")

        # Chạy tới khi stop
        stop_task = asyncio.create_task(stop_event.wait())
        disc_task = asyncio.create_task(client.disconnected)
        done, _ = await asyncio.wait(
            {stop_task, disc_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in (stop_task, disc_task):
            if not t.done():
                t.cancel()

        # Cancel pending click tasks
        for t in list(pending):
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        await log(f"[{tag}] ⛔ DUYỆT NẠP đã dừng")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
