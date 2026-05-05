"""團戰紀錄抓取 — 試跑腳本

目的：驗證點塔 → 紀錄頁 → 切攻擊 → 點 3 筆紀錄 → 關閉 → 返回 整條流程
本次只跑 1 塔（MarcoPanda），存診斷截圖 explore-XX.png
"""

import asyncio
import sys
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:63559"
CANVAS_SEL = "section.webrtc canvas"

# 標準座標：1920×1080（從使用者上傳截圖估算）
BASE_W, BASE_H = 1920, 1080

# 試跑只用「哈兔大聯盟」（左區，上偏右，明顯非空塔）
# 紅框估算（1334×750 系）→ 換成 1920×1080 標準
TEST_TOWER = ("哈兔大聯盟", int(0.611 * 1920), int(0.220 * 1080))  # (1173, 237)

UI_PX = {
    "back":          (95, 75),      # 左上 < 騎士團團戰
    "filter_all":    (1750, 175),   # 右上「全部」
    "filter_attack": (1750, 320),   # 下拉「攻擊」
    # 從使用者實際點擊抓到的精確位置（canvas px → 1920×1080 換算）
    "record_1":      (1853, 268),   # canvas (1223, 177)
    "record_2":      (1844, 401),   # canvas (1218, 265)
    "record_3":      (1843, 540),   # canvas (1217, 356)
    "close_battle":  (960, 108),    # 上方空白 ratio (0.5, 0.1)
}

DELAY_AFTER_CLICK = 3.0
DELAY_AFTER_FILTER = 5.0


async def get_offset(page):
    canvas = await page.query_selector(CANVAS_SEL)
    box = await canvas.bounding_box()
    return {"ox": box["x"], "oy": box["y"], "cw": box["width"], "ch": box["height"]}


def to_page_xy(px, py, off):
    nx, ny = px / BASE_W, py / BASE_H
    return nx * off["cw"] + off["ox"], ny * off["ch"] + off["oy"]


async def shoot(page, off, name):
    clip = {"x": max(0, off["ox"]), "y": off["oy"],
            "width": off["cw"] + min(0, off["ox"]), "height": off["ch"]}
    await page.screenshot(path=name, clip=clip, type="png")
    print(f"  [截圖] {name}")


async def click_px(page, off, px, py, label="", double=False):
    cx, cy = to_page_xy(px, py, off)
    await page.mouse.click(cx, cy)
    if double:
        await page.mouse.click(cx, cy)
    print(f"  [{'雙擊' if double else '點擊'}] {label} ({px},{py})@1920×1080 → page({cx:.0f},{cy:.0f})")


async def step(label, fn):
    print(f"\n--- {label} ---")
    await fn()


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = b.contexts[0]
        pg = next((p for p in ctx.pages if "ldcloud" in p.url), ctx.pages[0])
        print(f"page: {pg.url}")
        off = await get_offset(pg)
        print(f"canvas: ox={off['ox']:.1f} oy={off['oy']:.1f} cw={off['cw']:.0f} ch={off['ch']:.0f}")

        await shoot(pg, off, "explore-00-region.png")

        name, tx, ty = TEST_TOWER
        await click_px(pg, off, tx, ty, f"塔 [{name}]")
        await asyncio.sleep(DELAY_AFTER_CLICK)
        await shoot(pg, off, "explore-01-tower.png")

        await click_px(pg, off, *UI_PX["filter_all"], "下拉「全部」")
        await asyncio.sleep(DELAY_AFTER_CLICK)
        await shoot(pg, off, "explore-02-dropdown.png")

        await click_px(pg, off, *UI_PX["filter_attack"], "選「攻擊」")
        await asyncio.sleep(DELAY_AFTER_FILTER)
        await shoot(pg, off, "explore-03-attack.png")

        for i in range(1, 4):
            await click_px(pg, off, *UI_PX[f"record_{i}"], f"第 {i} 筆紀錄")
            await asyncio.sleep(DELAY_AFTER_CLICK)
            await shoot(pg, off, f"explore-04-record{i}.png")
            await click_px(pg, off, *UI_PX["close_battle"], "上方退出")
            await asyncio.sleep(DELAY_AFTER_CLICK)
            await shoot(pg, off, f"explore-05-after-close{i}.png")

        await click_px(pg, off, *UI_PX["back"], "< 騎士團團戰")
        await asyncio.sleep(DELAY_AFTER_CLICK)
        await shoot(pg, off, "explore-06-back.png")

        print("\n[完成]")


if __name__ == "__main__":
    asyncio.run(main())
