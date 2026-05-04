---
name: 雷電雲手機 LDCloud 技術參考
description: LDCloud 雲端手機平台的技術細節，包含 WebRTC 串流、LDSDK 事件格式、網頁版操作方式
type: reference
---

- 官網: https://ldcloud.net/
- 網頁版入口: https://www.ldcloud.net/web?locale=zh-TW
- 裝置操作頁: `https://www.ldcloud.net/web/webRtcNew?deviceId={id}&type=my`
- 串流方式: WebRTC（透過 LDSDK）
- 畫面渲染: `<canvas>` 元素，在 `<section class="webrtc">` 內
- LDSDK 版本: v1.2.6-5（beta）
- 觸控事件格式: JSON `{ seq, type:0, sub_type:10001(touch_start)/10002(touch_move), name:"touch_event" }`
- 不支援 ADB 遠端連線
- 支援平台: Android App / Windows App / iOS App / 網頁版
- 客服時間: 8:00-24:00 (UTC+8)
- Discord 官方社群: https://discord.gg/Z6qbb5PG4c
