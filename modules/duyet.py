"""DUYỆT NẠP – auto bấm nút "✅ Duyệt" trong tin nhắn của bot nạp tiền.

Cách hoạt động:
- Mở session telethon đã chọn.
- Lắng nghe NewMessage + MessageEdited.
- Chỉ xử lý tin có timestamp >= thời điểm BẬT TOOL (không quét tin cũ).
- Khi text chứa trigger -> chờ `delay` giây, refetch message,
  tìm inline button có chữ "Duyệt" và bấm.
- Chạy liên tục cho đến khi stop_event được set (bấm STOP).
"""
import asyncio
import time
from datetime import datetime, timezone

from telethon import events
from telethon.errors import FloodWaitError

from .session_mgr import make_client


async def _click_duyet(client, msg, button_text, log, tag):
    try:
        fresh = await client.get_messages(msg.chat_id, ids=msg.id)
    except Exception as e:
        await log(f"[{tag}] ❌ Lỗi refetch msg_id={msg.id}: {e}")
        return
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
    handled_ids: set[int] = set()  # dedupe NewMessage + MessageEdited
    # Thời điểm bật tool – chỉ xử lý tin từ lúc này trở đi
    start_ts = datetime.now(timezone.utc)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            await log(f"[{tag}] ❌ Session die")
            return

        bot_uname = bot_username.lstrip("@")
        try:
            bot_entity = await client.get_entity(bot_uname)
            bot_id = bot_entity.id
        except Exception as e:
            await log(f"[{tag}] ❌ Không tìm thấy bot @{bot_uname}: {e}")
            return

        await log(f"[{tag}] 🚀 DUYỆT NẠP đang chạy")
        await log(f"[{tag}] 👀 Bot: @{bot_uname} (id={bot_id}) | "
                  f"trigger='{trigger}' | delay={delay}s | button='{button_text}'")
        await log(f"[{tag}] ⏱ Chỉ duyệt tin nhận từ {start_ts.strftime('%H:%M:%S')} UTC trở đi")

        async def schedule(msg):
            await log(f"[{tag}] ⏳ Phát hiện lệnh nạp (msg_id={msg.id}), "
                      f"chờ {delay}s rồi bấm Duyệt…")
            try:
                # chờ theo từng giây để stop ngay khi user bấm STOP
                slept = 0.0
                step = 0.5
                while slept < delay:
                    if stop_event.is_set():
                        return
                    await asyncio.sleep(min(step, delay - slept))
                    slept += step
                await _click_duyet(client, msg, button_text, log, tag)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                await log(f"[{tag}] ❌ {e}")

        async def _process(event, source: str):
            try:
                msg = event.message
                # Bỏ qua tin cũ hơn thời điểm bật tool
                if msg.date and msg.date < start_ts:
                    return
                # Chỉ xét tin của đúng bot mục tiêu
                sender_id = getattr(msg, "sender_id", None)
                if sender_id != bot_id:
                    return
                text = msg.message or ""
                if trigger.lower() not in text.lower():
                    return
                if msg.id in handled_ids:
                    return
                handled_ids.add(msg.id)
                await log(f"[{tag}] 🔔 Khớp trigger qua {source} (msg_id={msg.id})")
                t = asyncio.create_task(schedule(msg))
                pending.add(t)
                t.add_done_callback(pending.discard)
            except Exception as e:
                await log(f"[{tag}] ❌ handler {source}: {e}")

        @client.on(events.NewMessage())
        async def _on_new(event):
            await _process(event, "NewMessage")

        @client.on(events.MessageEdited())
        async def _on_edit(event):
            await _process(event, "MessageEdited")

        # Chạy tới khi stop hoặc client disconnect
        stop_task = asyncio.create_task(stop_event.wait())
        disc_task = asyncio.ensure_future(client.disconnected)
        await asyncio.wait(
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
