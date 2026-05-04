#!/usr/bin/env python3
"""E7 秘密商店 — 雲端手機自動刷書籤

流程（每輪）：
  頂部找書籤 → 有則購買 → 捲動 → 底部找書籤 → 有則購買 → 無則更新商店 → 重複

停止條件：更新商店達 MAX_REFRESH 次
結束後將結果寫入 stats.json
"""

import aircv
import cv2
import numpy as np
import asyncio
import json
import os
import sys
import time
from playwright.async_api import async_playwright

# === 設定 ===
DRY_RUN = False
MAX_REFRESH = 500
DELAY_BEFORE_SCREENSHOT = 1.0  # 操作後等多久再截圖
DELAY_BEFORE_ACTION = 1.0     # 截圖後等多久再操作
MAX_CONSECUTIVE_ERRORS = 3    # 連續失敗幾次就退出
STATS_FILE = "stats.json"
PAUSE_FLAG = "pause.flag"     # 對話框未出現時建立此檔，外部刪除後繼續
PAUSE_POLL_SECONDS = 2        # 等待解除暫停的輪詢間隔

DEVICE_ID = "4713105"
LDCLOUD_URL = f"https://www.ldcloud.net/web/webRtcNew?deviceId={DEVICE_ID}&type=my"
CANVAS_SEL = "section.webrtc canvas"

# 範本路徑（雲端手機版）
COVENANT_TPL = "img/cloud/covenantLocation.png"
MYSTIC_TPL = "img/cloud/mysticLocation.png"
DIALOG_BUY_COVENANT_TPL = "img/cloud/dialogBuyButton-zh-TW.png"        # 184,000
DIALOG_BUY_MYSTIC_TPL = "img/cloud/dialogBuyButton-mystic-zh-TW.png"  # 280,000
REFRESH_TPL = "img/cloud/refreshButton-zh-TW.png"
REFRESH_YES_TPL = "img/cloud/refreshYesButton-zh-TW.png"

# 辨識閾值
BOOKMARK_CONF = 0.9
DIALOG_CONF = 0.9
REFRESH_CONF = 0.9

# 滑動參數
SWIPE_X = 846
SWIPE_TOP_Y = 206
SWIPE_BOT_Y = 382
SWIPE_STEPS = 15
SWIPE_DELAY_MS = 20


# === 統計 ===

class Stats:
    def __init__(self):
        self.start_time = time.time()
        self.refresh_count = 0
        self.covenant_count = 0
        self.mystic_count = 0
        self.errors = []

    @property
    def stones_spent(self):
        return self.refresh_count * 3

    @property
    def gold_spent(self):
        return self.covenant_count * 184000 + self.mystic_count * 280000

    @property
    def elapsed(self):
        return time.time() - self.start_time

    def save(self):
        data = {
            "start_time": self.start_time,
            "refresh_count": self.refresh_count,
            "covenant_count": self.covenant_count,
            "mystic_count": self.mystic_count,
            "stones_spent": self.stones_spent,
            "gold_spent": self.gold_spent,
            "elapsed_seconds": int(self.elapsed),
            "errors": self.errors[-10:],  # 只保留最近 10 筆錯誤
        }
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def report(self):
        mins = int(self.elapsed // 60)
        secs = int(self.elapsed % 60)
        return (
            f"===== 結算 =====\n"
            f"共花費:\n"
            f"天空石: {self.stones_spent}個\n"
            f"金幣: {self.gold_spent:,}元\n"
            f"獲得書籤:\n"
            f"聖約: {self.covenant_count}次\n"
            f"神秘: {self.mystic_count}次\n"
            f"總共刷新: {self.refresh_count}次\n"
            f"總共用時: {mins}分 {secs}秒"
        )


# === 座標換算 ===

def canvas_offset(page_box):
    return {
        "ox": page_box["x"],
        "oy": page_box["y"],
        "cw": page_box["width"],
        "ch": page_box["height"],
    }


def canvas_to_page(cx, cy, offset):
    """標準座標(1160x635) → page 座標，自動按實際 canvas 尺寸縮放"""
    scale_x = offset["cw"] / STANDARD_WIDTH
    scale_y = offset["ch"] / STANDARD_HEIGHT
    return cx * scale_x + offset["ox"], cy * scale_y + offset["oy"]


# === 瀏覽器操作 ===

async def get_canvas_info(page):
    canvas = await page.query_selector(CANVAS_SEL)
    box = await canvas.bounding_box()
    info = canvas_offset(box)
    print(f"  Canvas offset=({info['ox']}, {info['oy']}), size={info['cw']}x{info['ch']}")
    return canvas, info


STANDARD_WIDTH = 1160
STANDARD_HEIGHT = 635

async def canvas_screenshot(page) -> np.ndarray:
    """截取 canvas 並縮放到標準尺寸，不受視窗大小影響"""
    await asyncio.sleep(DELAY_BEFORE_SCREENSHOT)
    box = await (await page.query_selector(CANVAS_SEL)).bounding_box()
    # clip 不能有負數座標
    clip_x = max(0, box["x"])
    clip_w = box["width"] + min(0, box["x"])
    png_bytes = await page.screenshot(
        clip={"x": clip_x, "y": box["y"], "width": clip_w, "height": box["height"]},
        type="png",
    )
    arr = np.frombuffer(png_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    # 縮放到標準尺寸（範本圖基準）
    if img.shape[1] != STANDARD_WIDTH or img.shape[0] != STANDARD_HEIGHT:
        img = cv2.resize(img, (STANDARD_WIDTH, STANDARD_HEIGHT), interpolation=cv2.INTER_AREA)
    return img


async def swipe(page, start_x, start_y, end_x, end_y):
    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    for i in range(1, SWIPE_STEPS + 1):
        x = start_x + (end_x - start_x) * (i / SWIPE_STEPS)
        y = start_y + (end_y - start_y) * (i / SWIPE_STEPS)
        await page.mouse.move(x, y)
        await asyncio.sleep(SWIPE_DELAY_MS / 1000)
    await page.mouse.up()


async def scroll_down(page, offset):
    """用標準座標換算後滑動"""
    sx, sy = canvas_to_page(SWIPE_X, SWIPE_BOT_Y, offset)
    ex, ey = canvas_to_page(SWIPE_X, SWIPE_TOP_Y, offset)
    await swipe(page, sx, sy, ex, ey)


async def scroll_to_top(page):
    for _ in range(3):
        await swipe(page, SWIPE_X, SWIPE_TOP_Y, SWIPE_X, SWIPE_BOT_Y)
        await asyncio.sleep(0.3)


async def click_at(page, canvas_x, canvas_y, offset):
    px, py = canvas_to_page(canvas_x, canvas_y, offset)
    await page.mouse.click(px, py)


async def double_click_at(page, canvas_x, canvas_y, offset):
    await asyncio.sleep(DELAY_BEFORE_ACTION)
    await click_at(page, canvas_x, canvas_y, offset)
    await click_at(page, canvas_x, canvas_y, offset)


# === 辨識 ===

def find_template(screenshot, template_path, threshold):
    tmpl = aircv.imread(template_path)
    if tmpl is None:
        return None
    return aircv.find_template(screenshot, tmpl, threshold)


def find_bookmarks(screenshot):
    """尋找所有書籤，回傳 [(類型, result), ...] 清單"""
    found = []
    covenant = find_template(screenshot, COVENANT_TPL, BOOKMARK_CONF)
    if covenant:
        print(f"  [找到] 聖約書籤 conf={covenant['confidence']:.3f}")
        found.append(("covenant", covenant))

    mystic = find_template(screenshot, MYSTIC_TPL, BOOKMARK_CONF)
    if mystic:
        print(f"  [找到] 神秘書籤 conf={mystic['confidence']:.3f}")
        found.append(("mystic", mystic))

    if not found:
        print(f"  [未找到] 書籤")
    return found


# === 暫停機制 ===

async def pause_for_intervention(page, btype, stats):
    """寫入 pause.flag 並截圖，等待外部刪除 flag 後繼續。

    使用情境：對話框未出現等異常狀態 — 由 Claude 看畫面、操作 LDCloud 恢復後
    刪除 pause.flag 解除暫停。
    """
    snapshot_path = f"pause-r{stats.refresh_count}-{btype}-{int(time.time())}.png"
    try:
        box = await (await page.query_selector(CANVAS_SEL)).bounding_box()
        clip_x = max(0, box["x"])
        clip_w = box["width"] + min(0, box["x"])
        await page.screenshot(
            path=snapshot_path,
            clip={"x": clip_x, "y": box["y"], "width": clip_w, "height": box["height"]},
            type="png",
        )
    except Exception as e:
        snapshot_path = f"(截圖失敗: {e})"

    info = (
        f"round={stats.refresh_count}\n"
        f"btype={btype}\n"
        f"reason=對話框未出現\n"
        f"snapshot={snapshot_path}\n"
        f"timestamp={time.time()}\n"
        f"\n"
        f"刪除此檔以繼續執行（程式會 skip 此書籤、繼續本輪餘下流程）。\n"
    )
    with open(PAUSE_FLAG, "w", encoding="utf-8") as f:
        f.write(info)
    print(f"  [PAUSE] 等待介入（snapshot={snapshot_path}）")
    print(f"  [PAUSE] 刪除 {PAUSE_FLAG} 以繼續")

    waited = 0
    while os.path.exists(PAUSE_FLAG):
        await asyncio.sleep(PAUSE_POLL_SECONDS)
        waited += PAUSE_POLL_SECONDS
        if waited % 60 == 0:
            print(f"  [PAUSE] 已等待 {waited}s …")
    print(f"  [RESUME] 已解除暫停（等待 {waited}s）")


# === 購買流程 ===

async def buy_bookmark(page, canvas, bookmark_pos, offset, btype, stats):
    bx, by = bookmark_pos
    dialog_tpl = DIALOG_BUY_COVENANT_TPL if btype == "covenant" else DIALOG_BUY_MYSTIC_TPL

    buy_area_x = bx + 498
    buy_area_y = by + 26

    if DRY_RUN:
        print(f"  [DRY_RUN] 跳過購買 {btype}")
        return False

    await double_click_at(page, buy_area_x, buy_area_y, offset)

    shot = await canvas_screenshot(page)
    dialog_buy = find_template(shot, dialog_tpl, DIALOG_CONF)
    if dialog_buy:
        dx, dy = dialog_buy["result"]
        await double_click_at(page, dx, dy, offset)

        shot2 = await canvas_screenshot(page)
        still_there = find_template(shot2, dialog_tpl, DIALOG_CONF)
        if still_there:
            await double_click_at(page, still_there["result"][0], still_there["result"][1], offset)

        if btype == "covenant":
            stats.covenant_count += 1
        else:
            stats.mystic_count += 1
        print(f"  [購買成功] {btype} (聖約={stats.covenant_count}, 神秘={stats.mystic_count})")
        return True
    else:
        stats.errors.append(f"round {stats.refresh_count}: 對話框未出現 ({btype})")
        print(f"  [購買失敗] 對話框未出現")
        await pause_for_intervention(page, btype, stats)
        return False


# === 更新商店 ===

async def refresh_shop(page, canvas, offset, stats):
    shot = await canvas_screenshot(page)
    result = find_template(shot, REFRESH_TPL, REFRESH_CONF)
    if not result:
        stats.errors.append(f"round {stats.refresh_count}: 找不到更新按鈕")
        print("  [錯誤] 找不到更新按鈕")
        return False

    rx, ry = result["result"]

    if DRY_RUN:
        print(f"  [DRY_RUN] 跳過更新")
        return False

    await double_click_at(page, rx, ry, offset)

    shot2 = await canvas_screenshot(page)
    yes_btn = find_template(shot2, REFRESH_YES_TPL, DIALOG_CONF)
    if yes_btn:
        yx, yy = yes_btn["result"]
        await double_click_at(page, yx, yy, offset)

        shot3 = await canvas_screenshot(page)
        still_there = find_template(shot3, REFRESH_YES_TPL, DIALOG_CONF)
        if still_there:
            await double_click_at(page, still_there["result"][0], still_there["result"][1], offset)

        stats.refresh_count += 1
        print(f"  [更新成功] 第 {stats.refresh_count}/{MAX_REFRESH} 次")
        return True
    else:
        stats.errors.append(f"round {stats.refresh_count}: 確認按鈕未出現")
        print("  [更新失敗] 確認按鈕未出現")
        return False


# === 主流程 ===

async def scan_and_buy(page, canvas, offset, shot, stats):
    """對已截取的畫面找所有書籤，逐一購買"""
    found = find_bookmarks(shot)
    for btype, result in found:
        await buy_bookmark(page, canvas, result["result"], offset, btype, stats)
        # 購買後畫面變化，重新截圖找下一個
        if len(found) > 1:
            shot = await canvas_screenshot(page)
    return len(found) > 0


async def run(page):
    print("=" * 40)
    print("E7 秘密商店 — 自動刷書籤")
    print(f"DRY_RUN={DRY_RUN}, MAX_REFRESH={MAX_REFRESH}")
    print("=" * 40)

    canvas, offset = await get_canvas_info(page)
    stats = Stats()
    consecutive_errors = 0

    while stats.refresh_count < MAX_REFRESH:
        n = stats.refresh_count + 1
        print(f"\n--- 輪 {n}/{MAX_REFRESH} ---")

        # 頂部
        shot_top = await canvas_screenshot(page)
        await scan_and_buy(page, canvas, offset, shot_top, stats)

        # 捲動
        await scroll_down(page, offset)

        # 底部
        shot_bot = await canvas_screenshot(page)
        await scan_and_buy(page, canvas, offset, shot_bot, stats)

        # 更新商店（更新後商店自動回頂部）
        ok = await refresh_shop(page, canvas, offset, stats)
        if ok:
            consecutive_errors = 0
        else:
            consecutive_errors += 1
            print(f"  [警告] 連續失敗 {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"\n[中斷] 連續 {MAX_CONSECUTIVE_ERRORS} 次失敗，退出等待檢查")
                break

        # 每 10 輪存檔
        if stats.refresh_count % 10 == 0:
            stats.save()
            print(f"  [存檔] {STATS_FILE}")

    # 結束
    stats.save()
    report = stats.report()
    completed = stats.refresh_count >= MAX_REFRESH
    print(f"\n{report}")
    return report, completed, stats


async def main():
    cdp_url = "http://localhost:63559"
    for arg in sys.argv[1:]:
        if arg.startswith("http"):
            cdp_url = arg

    async with async_playwright() as p:
        try:
            print(f"連接瀏覽器 {cdp_url}...")
            browser = await p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            page = None
            for pg in context.pages:
                if "ldcloud" in pg.url:
                    page = pg
                    break
            if not page:
                page = context.pages[0]
            print(f"已連接: {page.url}")
        except Exception as e:
            print(f"連接失敗: {e}")
            return

        report, completed, stats = await run(page)

        # 寫入報告供外部讀取
        with open("report.txt", "w", encoding="utf-8") as f:
            f.write(report)

        if completed:
            print("\n[完成] 已達目標次數")
        else:
            print(f"\n[中斷] 已完成 {stats.refresh_count}/{MAX_REFRESH} 次，等待檢查後繼續")


if __name__ == "__main__":
    asyncio.run(main())
