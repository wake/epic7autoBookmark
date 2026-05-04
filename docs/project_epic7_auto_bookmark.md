---
name: Epic7 自動刷秘密商店專案
description: 將 epic7autoBookmark 移植到 Mac + 雷電雲手機的可行性研究與驗證結果
type: project
---

## 目標

將 GitHub 專案 `Raven9527/epic7autoBookmark`（第七史詩自動刷秘密商店工具）改造為在 Mac 上透過雷電雲手機（LDCloud）運行。

## 原始工具架構

- 單檔 Python 應用（`main.py`，~762 行）
- GUI: PyQt6 + QThread
- 圖像辨識: aircv (OpenCV template matching)
- 遊戲操控: adbutils → ADB → BlueStacks (Windows)
- 解析度: 硬編碼 1920x1080
- 支援語系: zh-TW / zh-CN / en-US
- 設定檔: `config.json`（ADB 位址、語系）、`conf/conf_config.json`（匹配閾值）

## 改造方案：Playwright 取代 ADB

雷電雲手機不支援 ADB，遊戲畫面透過 WebRTC 串流到瀏覽器的 `<canvas>` 元素。

**Why:** 雲端手機廠商不開放 ADB 埠，只能透過瀏覽器介面操作。
**How to apply:** 將約 10 幾處 ADB 呼叫替換為 Playwright 瀏覽器操作，辨識邏輯（OpenCV）不需修改。

## 2026-03-24 驗證結果

在 LDCloud 網頁版（`ldcloud.net/web/webRtcNew`）上實測：

| 測試項目 | 結果 | 備註 |
|---------|------|------|
| Playwright 截圖 | ✅ 成功 | 畫面清晰，可供 OpenCV 辨識 |
| 滑動（swipe） | ✅ 成功 | page.mouse down/move/up，分 15 步，每步 20ms |
| 觸控事件傳遞 | ✅ 確認 | LDSDK 收到 touch 事件（sub_type 10001/10002） |
| 點擊購買 | 未測試 | 會花遊戲金幣，待後續測試 |

### Canvas 資訊

- 元素: `<canvas>` 在 `<section class="webrtc">` 內
- 位置: x=0.5, y=88.5
- 顯示尺寸: 1160x635（橫向）
- 遊戲內部解析度: 720x1280（直向，由 LDSDK 旋轉）

### 秘密商店結構

- 每次刷新 6 個商品
- 一頁約顯示 4.5 個，滑動一次即可看到全部
- 商品類型: 裝備、財物（友情點數）、書籤（聖約/神秘）

## 需要的修改清單

1. `adb.connect()` → Playwright 啟動/連接瀏覽器
2. `device.screenshot()` → `page.screenshot()` 或 canvas 截圖
3. `device.click(x, y)` → `page.mouse.click(x, y)`（需座標轉換）
4. `device.swipe()` → `page.mouse` 分段拖曳（15 步 × 20ms）
5. 硬編碼座標 1920x1080 → 依 canvas 尺寸重新校準
6. `img/` 範本圖片 → 可能需根據雲端手機畫質重新截圖
7. config 中 ADB 設定 → 改為瀏覽器 URL 設定

## 雷電雲手機帳號

- 平台: LDCloud（ldcloud.net）
- 裝置名稱: E7專用1號（deviceId: 4713105）
- 另有裝置 deviceId: 4712121
- 網頁版 URL 格式: `ldcloud.net/web/webRtcNew?deviceId={id}&type=my`
