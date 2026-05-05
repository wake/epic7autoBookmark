"""左區 13 塔完整流程

對 13 塔依序執行：
  進塔 → 確認紀錄頁 → 切「攻擊」filter → 抓 3 筆紀錄（驗證 VS）→ 返回

截圖存到 guild-records/{YYYY-MM-DD}/left-tower{NN}-attack-{N}.png
空塔自動跳過；不滿 3 筆紀錄自動跳過該筆
"""

import asyncio
import cv2
import aircv
import datetime
import os
import numpy as np
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:63559"
CANVAS_SEL = "section.webrtc canvas"

TPL_SEASON      = "img/cloud/season_record_label.png"
TPL_FILTER_ALL  = "img/cloud/filter_all_button.png"
TPL_FILTER_ATK  = "img/cloud/filter_attack_button.png"
TPL_DROPDOWN_ATK= "img/cloud/dropdown_attack_option.png"
TPL_BATTLE_VS   = "img/cloud/battle_vs_label.png"

CONF = 0.85
REGION = "left"

LEFT_TOWERS_CANVAS = [
    (354, 187),   # 01
    (239, 354),   # 02  - 空塔
    (181, 518),   # 03  - 空塔
    (325, 561),   # 04
    (473, 466),   # 05
    (631, 335),   # 06
    (802, 143),   # 07  - 哈兔
    (891, 268),   # 08
    (774, 454),   # 09
    (621, 602),   # 10
    (870, 593),   # 11  - 空塔
    (986, 396),   # 12
    (1093, 542),  # 13
]

UI_CANVAS = {
    "back":             (38, 33),
    "filter_dropdown":  (1154, 99),
    "record_1":         (1223, 177),
    "record_2":         (1218, 265),
    "record_3":         (1217, 356),
    "exit_battle":      (634, 71),
}


async def get_offset(page):
    canvas = await page.query_selector(CANVAS_SEL)
    box = await canvas.bounding_box()
    return {"ox": box["x"], "oy": box["y"], "cw": box["width"], "ch": box["height"]}


async def click_canvas(page, off, cx, cy, label=""):
    px, py = cx + off["ox"], cy + off["oy"]
    await page.mouse.click(px, py)
    print(f"  [點擊] {label} canvas({cx},{cy})")


async def screenshot_1080(page, off):
    clip = {"x": max(0, off["ox"]), "y": off["oy"],
            "width": off["cw"] + min(0, off["ox"]), "height": off["ch"]}
    png = await page.screenshot(clip=clip, type="png")
    arr = np.frombuffer(png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return cv2.resize(img, (1920, 1080), interpolation=cv2.INTER_AREA)


def match_conf(img1080, tpl_path, conf=CONF):
    r = aircv.find_template(img1080, aircv.imread(tpl_path), conf)
    return r["confidence"] if r else None


def match_pos(img1080, tpl_path, conf=CONF):
    r = aircv.find_template(img1080, aircv.imread(tpl_path), conf)
    return r if r else None


async def switch_to_attack(page, off):
    img = await screenshot_1080(page, off)
    if match_conf(img, TPL_FILTER_ATK):
        return True
    if not match_conf(img, TPL_FILTER_ALL):
        return False

    await click_canvas(page, off, *UI_CANVAS["filter_dropdown"], "下拉")
    await asyncio.sleep(1)

    img = await screenshot_1080(page, off)
    r = match_pos(img, TPL_DROPDOWN_ATK)
    if not r:
        return False
    rx_1080, ry_1080 = r["result"]
    rx = int(rx_1080 / 1920 * off["cw"])
    ry = int(ry_1080 / 1080 * off["ch"])
    await click_canvas(page, off, rx, ry, f"下拉攻擊 conf={r['confidence']:.3f}")
    await asyncio.sleep(5)

    img = await screenshot_1080(page, off)
    return bool(match_conf(img, TPL_FILTER_ATK))


async def process_tower(page, off, idx, cx, cy, out_dir):
    print(f"\n=== 塔 {idx:02d}/13 canvas({cx},{cy}) ===")
    await click_canvas(page, off, cx, cy, f"塔 {idx:02d}")
    await asyncio.sleep(3)

    img = await screenshot_1080(page, off)
    if not match_conf(img, TPL_SEASON):
        print(f"  [空塔] 未進入紀錄頁，跳過")
        return {"idx": idx, "kind": "empty", "records": 0}

    if not await switch_to_attack(page, off):
        print(f"  [錯誤] filter 切換失敗")
        await click_canvas(page, off, *UI_CANVAS["back"], "< 返回")
        await asyncio.sleep(3)
        return {"idx": idx, "kind": "filter_error", "records": 0}

    saved = 0
    for i in range(1, 4):
        await click_canvas(page, off, *UI_CANVAS[f"record_{i}"], f"record_{i}")
        await asyncio.sleep(3)
        img = await screenshot_1080(page, off)
        vs_conf = match_conf(img, TPL_BATTLE_VS)
        if not vs_conf:
            print(f"  [第 {i} 筆] 未開啟，跳過")
            continue
        save = f"{out_dir}/{REGION}-tower{idx:02d}-attack-{i}.png"
        cv2.imwrite(save, img)
        saved += 1
        print(f"  [第 {i} 筆] 截圖 {save} (VS conf={vs_conf:.3f})")
        await click_canvas(page, off, *UI_CANVAS["exit_battle"], "上方退出")
        await asyncio.sleep(3)

    await click_canvas(page, off, *UI_CANVAS["back"], "< 返回")
    await asyncio.sleep(3)
    return {"idx": idx, "kind": "filled", "records": saved}


async def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    out_dir = f"guild-records/{today}"
    os.makedirs(out_dir, exist_ok=True)
    print(f"輸出目錄: {out_dir}\n")

    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = b.contexts[0]
        pg = next((p for p in ctx.pages if "ldcloud" in p.url), ctx.pages[0])
        off = await get_offset(pg)
        print(f"canvas: cw={off['cw']:.0f} ch={off['ch']:.0f}")

        results = []
        for i, (cx, cy) in enumerate(LEFT_TOWERS_CANVAS, 1):
            r = await process_tower(pg, off, i, cx, cy, out_dir)
            results.append(r)

        print("\n=== 結算 ===")
        empty = sum(1 for r in results if r["kind"] == "empty")
        filled = sum(1 for r in results if r["kind"] == "filled")
        errors = sum(1 for r in results if r["kind"] == "filter_error")
        total_records = sum(r["records"] for r in results)
        print(f"空塔: {empty}, 有頭像: {filled}, filter 錯誤: {errors}")
        print(f"截圖總數: {total_records}\n")
        for r in results:
            print(f"  塔 {r['idx']:02d}: {r['kind']:15s} records={r['records']}")


if __name__ == "__main__":
    asyncio.run(main())
