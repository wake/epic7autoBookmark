"""依序點 13 個塔位，用「賽季紀錄」模板比對是否進入紀錄頁。

進入 → 印「有頭像」+ 點 < 返回 → sleep 3
未進入 → 印「空塔」+ 直接點下一個

使用者抓到的 13 塔位 + UI 座標（canvas 1268×713 系，S 形順序）
"""

import asyncio
import cv2
import aircv
import numpy as np
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:63559"
CANVAS_SEL = "section.webrtc canvas"
SEASON_RECORD_TPL = "img/cloud/season_record_label.png"
SEASON_RECORD_CONF = 0.85

# 13 塔座標（canvas px，使用者實際點擊抓到）
LEFT_TOWERS_CANVAS = [
    (354, 187),   # 1
    (239, 354),   # 2
    (181, 518),   # 3
    (325, 561),   # 4
    (473, 466),   # 5
    (631, 335),   # 6
    (802, 143),   # 7
    (891, 268),   # 8
    (774, 454),   # 9
    (621, 602),   # 10
    (870, 593),   # 11
    (986, 396),   # 12
    (1093, 542),  # 13
]

BACK_BUTTON_CANVAS = (38, 33)  # < 騎士團團戰


async def get_offset(page):
    canvas = await page.query_selector(CANVAS_SEL)
    box = await canvas.bounding_box()
    return {"ox": box["x"], "oy": box["y"], "cw": box["width"], "ch": box["height"]}


async def click_canvas(page, off, cx, cy, label=""):
    px, py = cx + off["ox"], cy + off["oy"]
    await page.mouse.click(px, py)
    print(f"  [點擊] {label} canvas({cx},{cy}) → page({px:.0f},{py:.0f})")


async def screenshot_resized(page, off):
    """截 canvas → resize 到 1920×1080（模板系）"""
    clip = {"x": max(0, off["ox"]), "y": off["oy"],
            "width": off["cw"] + min(0, off["ox"]), "height": off["ch"]}
    png = await page.screenshot(clip=clip, type="png")
    arr = np.frombuffer(png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return cv2.resize(img, (1920, 1080), interpolation=cv2.INTER_AREA)


async def is_in_record_page(page, off):
    img = await screenshot_resized(page, off)
    tpl = aircv.imread(SEASON_RECORD_TPL)
    r = aircv.find_template(img, tpl, SEASON_RECORD_CONF)
    return r["confidence"] if r else None


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = b.contexts[0]
        pg = next((p for p in ctx.pages if "ldcloud" in p.url), ctx.pages[0])
        off = await get_offset(pg)
        print(f"canvas: ox={off['ox']:.1f} oy={off['oy']:.1f} cw={off['cw']:.0f} ch={off['ch']:.0f}\n")

        result = []
        for i, (cx, cy) in enumerate(LEFT_TOWERS_CANVAS, 1):
            print(f"--- 塔 {i:2d}/13 ---")
            await click_canvas(pg, off, cx, cy, f"塔 {i}")
            await asyncio.sleep(3)

            conf = await is_in_record_page(pg, off)
            if conf:
                print(f"  [進入] 賽季紀錄 conf={conf:.3f} → 有頭像，點返回")
                result.append((i, cx, cy, "filled", conf))
                await click_canvas(pg, off, *BACK_BUTTON_CANVAS, "< 返回")
                await asyncio.sleep(3)
            else:
                print(f"  [空塔] 賽季紀錄未顯現 → 跳過")
                result.append((i, cx, cy, "empty", None))

        print("\n=== 結果 ===")
        empty = sum(1 for r in result if r[3] == "empty")
        filled = sum(1 for r in result if r[3] == "filled")
        print(f"空塔: {empty}, 有頭像: {filled}")
        for i, cx, cy, kind, conf in result:
            tag = f"conf={conf:.3f}" if conf else "—"
            print(f"  塔 {i:2d} ({cx:4d},{cy:3d}): {kind:6s} {tag}")


if __name__ == "__main__":
    asyncio.run(main())
