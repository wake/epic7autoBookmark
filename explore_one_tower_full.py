"""對單塔（哈兔 = 塔 7）試跑完整 record 抓取流程

流程：
  點塔 → 等 3 → 確認進入紀錄頁（賽季紀錄）
  比對 all.png：
    抓到 → 點下拉 → 等 1 → 比對 dropdown-attack：
      抓到 → 點該選項 → 等 5
      沒抓到 → 退出此塔
    沒抓到 → 直接進下一步
  比對 attack.png：
    抓到 → 抓 3 筆紀錄
    沒抓到 → 退出此塔
  for i in 1..3:
    點 record_i → 等 3 → 截圖保存 → 點上方退出 → 等 3
  點 < 返回 → 等 3
"""

import asyncio
import cv2
import aircv
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

# 哈兔（塔 7） — canvas 系
TARGET_TOWER = (802, 143, "tower07")

UI_CANVAS = {
    "back":             (38, 33),
    "filter_dropdown":  (1154, 99),    # 點開下拉
    "record_1":         (1223, 177),
    "record_2":         (1218, 265),
    "record_3":         (1217, 356),
    "exit_battle":      (634, 71),     # 上方空白（彈窗外）
}

REGION = "left"  # 之後擴展時用


async def get_offset(page):
    canvas = await page.query_selector(CANVAS_SEL)
    box = await canvas.bounding_box()
    return {"ox": box["x"], "oy": box["y"], "cw": box["width"], "ch": box["height"]}


async def click_canvas(page, off, cx, cy, label=""):
    px, py = cx + off["ox"], cy + off["oy"]
    await page.mouse.click(px, py)
    print(f"  [點擊] {label} canvas({cx},{cy})")


async def screenshot_1080(page, off, save_path=None):
    clip = {"x": max(0, off["ox"]), "y": off["oy"],
            "width": off["cw"] + min(0, off["ox"]), "height": off["ch"]}
    png = await page.screenshot(clip=clip, type="png")
    arr = np.frombuffer(png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    img1080 = cv2.resize(img, (1920, 1080), interpolation=cv2.INTER_AREA)
    if save_path:
        cv2.imwrite(save_path, img1080)
    return img1080


def match(img1080, tpl_path, conf=CONF):
    tpl = aircv.imread(tpl_path)
    r = aircv.find_template(img1080, tpl, conf)
    return r["confidence"] if r else None


async def attempt_switch_to_attack(page, off):
    """嘗試把 filter 切到「攻擊」。回傳 True/False/None
    True  = 切換成功（或本來就是攻擊）
    False = 失敗（下拉沒出現攻擊選項等）
    """
    img = await screenshot_1080(page, off)
    if match(img, TPL_FILTER_ATK):
        print(f"  [filter] 已是「攻擊」，跳過切換")
        return True
    if not match(img, TPL_FILTER_ALL):
        print(f"  [filter] 既不是 全部 也不是 攻擊？")
        return False

    print(f"  [filter] 偵測到「全部」→ 點下拉")
    await click_canvas(page, off, *UI_CANVAS["filter_dropdown"], "下拉")
    await asyncio.sleep(1)

    img = await screenshot_1080(page, off)
    r = aircv.find_template(img, aircv.imread(TPL_DROPDOWN_ATK), CONF)
    if not r:
        print(f"  [filter] 下拉內找不到「攻擊」選項")
        return False
    rx_1080, ry_1080 = r["result"]
    rx_canvas = rx_1080 / 1920 * off["cw"]
    ry_canvas = ry_1080 / 1080 * off["ch"]
    print(f"  [filter] 下拉中「攻擊」位於 canvas({rx_canvas:.0f},{ry_canvas:.0f}) conf={r['confidence']:.3f}")
    await click_canvas(page, off, int(rx_canvas), int(ry_canvas), "下拉攻擊")
    await asyncio.sleep(5)
    return True


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(CDP_URL)
        ctx = b.contexts[0]
        pg = next((p for p in ctx.pages if "ldcloud" in p.url), ctx.pages[0])
        off = await get_offset(pg)

        tx, ty, name = TARGET_TOWER
        print(f"=== 試跑塔 [{name}] canvas({tx},{ty}) ===")

        await click_canvas(pg, off, tx, ty, name)
        await asyncio.sleep(3)

        img = await screenshot_1080(pg, off)
        if not match(img, TPL_SEASON):
            print(f"[失敗] 未進入紀錄頁，退出")
            return
        print(f"[OK] 已進入紀錄頁\n")

        if not await attempt_switch_to_attack(pg, off):
            print(f"[退出] filter 切換失敗，點返回")
            await click_canvas(pg, off, *UI_CANVAS["back"], "< 返回")
            return

        img = await screenshot_1080(pg, off)
        if not match(img, TPL_FILTER_ATK):
            print(f"[退出] 切換後仍非「攻擊」filter")
            await click_canvas(pg, off, *UI_CANVAS["back"], "< 返回")
            return
        print(f"[OK] filter 已是「攻擊」，開始抓紀錄\n")

        # 抓三筆紀錄（驗證彈窗有開才存圖）
        for i in range(1, 4):
            print(f"--- 第 {i} 筆 ---")
            await click_canvas(pg, off, *UI_CANVAS[f"record_{i}"], f"record_{i}")
            await asyncio.sleep(3)
            img = await screenshot_1080(pg, off)
            vs_conf = match(img, TPL_BATTLE_VS)
            if not vs_conf:
                print(f"  [跳過] 彈窗未開啟（可能少於 {i} 筆紀錄）")
                continue
            save = f"guild-{REGION}-{name}-attack-{i}.png"
            cv2.imwrite(save, img)
            print(f"  [截圖] {save} (VS conf={vs_conf:.3f})")
            await click_canvas(pg, off, *UI_CANVAS["exit_battle"], "上方退出")
            await asyncio.sleep(3)

        await click_canvas(pg, off, *UI_CANVAS["back"], "< 返回")
        await asyncio.sleep(3)
        print(f"\n[完成] 塔 [{name}] 流程結束")


if __name__ == "__main__":
    asyncio.run(main())
