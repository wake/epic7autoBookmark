"""監聽你的手動 click，印出 (page x, y) + (canvas relative x, y)

usage: capture_click.py [seconds]    (default 60)
"""

import asyncio, sys
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://localhost:63559")
        ctx = b.contexts[0]
        pg = next((p for p in ctx.pages if "ldcloud" in p.url), ctx.pages[0])

        canvas = await pg.query_selector("section.webrtc canvas")
        box = await canvas.bounding_box()
        ox, oy, cw, ch = box["x"], box["y"], box["width"], box["height"]
        print(f"canvas: ox={ox:.1f} oy={oy:.1f} cw={cw:.0f} ch={ch:.0f}")

        pg.on("console", lambda msg: print(f"  → {msg.text}"))

        await pg.evaluate(f"""() => {{
            const c = document.querySelector('section.webrtc canvas');
            const rect = c.getBoundingClientRect();
            const log = (type, e) => {{
                const cx = e.clientX - rect.left;
                const cy = e.clientY - rect.top;
                console.log(`${{type}} page(${{e.clientX}},${{e.clientY}}) canvas(${{cx.toFixed(0)}},${{cy.toFixed(0)}}) ratio(${{(cx/rect.width).toFixed(3)}},${{(cy/rect.height).toFixed(3)}})`);
            }};
            for (const t of ['mousedown','mouseup','click','pointerdown','pointerup']) {{
                window.addEventListener(t, (e) => log(t.toUpperCase(), e), true);
            }}
            console.log('listeners installed');
        }}""")

        timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 60
        print(f"\n👉 請在 Chrome 內點任意位置，{timeout} 秒內可以多點幾次")
        await asyncio.sleep(timeout)
        print("\n[結束聽筒]")


if __name__ == "__main__":
    asyncio.run(main())
