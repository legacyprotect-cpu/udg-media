#!/usr/bin/env python3
"""Uncommon Discounts Galore: daily faceless video maker.

Usage:
  python3 make_video.py spec.json out.mp4

The kit folder holds scenes.html, make_video.py and img/{gas,groceries,airfare,seasonal}.jpg.
Needs: Python packages playwright, kokoro-onnx, soundfile, numpy, pillow; Google Chrome;
ffmpeg. The Kokoro voice model (Apache-2.0) is downloaded on first run.

spec.json fields (all text plain, no em dashes, no coupon codes):
  photo: gas | groceries | airfare | seasonal
  hook:  {kicker, l1, big, l3}          scene 1 on-screen text
  deal:  {fig, title, chips:[..], fine}  scene 2 on-screen text
  count: {big, sub, tiles:[{cat, n}]}    scene 3 on-screen text
  price: "$8"
  vo:    {s1, s2, s3, s4a, s4b, s4c, s5} voiceover lines (spell numbers and hard names as spoken)
  forbid: [..]  coupon codes that must never appear anywhere in the video
"""
import asyncio, json, os, subprocess, sys, tempfile, urllib.request

KIT = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.environ.get("KOKORO_DIR", os.path.expanduser("~/kokoro"))
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FPS, SR = 30, 24000
VOICE, SPEED = "af_heart", 1.08
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")


def fail(msg):
    print("ERROR", msg); sys.exit(1)


def check_spec(spec):
    texts = []
    def walk(v):
        if isinstance(v, str): texts.append(v)
        elif isinstance(v, dict): [walk(x) for k, x in v.items() if k != "forbid"]
        elif isinstance(v, list): [walk(x) for x in v]
    walk(spec)
    for t in texts:
        if "—" in t: fail(f"em dash in spec text: {t!r}")
    for code in spec.get("forbid", []):
        for t in texts:
            if code and code.upper() in t.upper(): fail(f"coupon code {code} appears in the video text: {t!r}")
    for k in ["s1", "s2", "s3", "s4a", "s4b", "s4c", "s5"]:
        if not spec.get("vo", {}).get(k): fail(f"vo.{k} missing")
    if spec.get("photo") not in ("gas", "groceries", "airfare", "seasonal"): fail("photo must be gas, groceries, airfare or seasonal")


def ensure_models():
    os.makedirs(MODEL_DIR, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = os.path.join(MODEL_DIR, f)
        if not os.path.exists(p) or os.path.getsize(p) < 1_000_000:
            print("downloading", f)
            urllib.request.urlretrieve(MODEL_URL + f, p)


def make_voice(spec, work):
    import numpy as np, soundfile as sf
    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"), os.path.join(MODEL_DIR, "voices-v1.0.bin"))
    durs = {}
    for key, text in spec["vo"].items():
        a, sr = k.create(text, voice=VOICE, speed=SPEED, lang="en-us")
        idx = np.where(np.abs(a) > 0.01)[0]
        a = a[max(idx[0] - int(.03 * sr), 0): idx[-1] + int(.08 * sr)]
        sf.write(os.path.join(work, f"{key}.wav"), a, sr)
        durs[key] = len(a) / sr
    return durs


async def shoot(spec, work):
    from playwright.async_api import async_playwright
    html = open(os.path.join(KIT, "scenes.html"), encoding="utf-8").read().replace("/*SPEC*/{}", json.dumps(spec))
    page_path = os.path.join(KIT, "_scenes_render.html")
    open(page_path, "w", encoding="utf-8").write(html)
    shots = [("s1", 1), ("s1", 0), ("s2", 0), ("s3", 0), ("s4", 1), ("s4", 2), ("s4", 3), ("s5", 0)]
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME)
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + page_path)
        await pg.evaluate("document.fonts.ready"); await pg.wait_for_timeout(1500)
        if errs: fail(f"scene page errors: {errs}")
        for sid, step in shots:
            await pg.evaluate(f"show('{sid}', {step})"); await pg.wait_for_timeout(250)
            await pg.screenshot(path=os.path.join(work, f"{sid}_{step}.jpg"), type="jpeg", quality=92)
        await b.close()
    os.remove(page_path)


def render(spec, durs, work, out):
    import numpy as np, soundfile as sf
    fr = lambda sec: max(1, round(sec * FPS))
    plan = [("s1_1", 0.7, "s1"), ("s1_0", durs["s1"] - 0.7 + 0.35, None),
            ("s2_0", durs["s2"] + 0.35, "s2"), ("s3_0", durs["s3"] + 0.35, "s3"),
            ("s4_1", durs["s4a"] + 0.15, "s4a"), ("s4_2", durs["s4b"] + 0.2, "s4b"), ("s4_3", durs["s4c"] + 0.4, "s4c"),
            ("s5_0", durs["s5"] + 1.3, "s5")]
    total = sum(fr(s) for _, s, _ in plan)
    track = np.zeros(int(total / FPS * SR) + SR, dtype=np.float32)
    lst, t = [], 0
    for i, (img, sec, clip) in enumerate(plan):
        n = fr(sec); dur = n / FPS
        if clip:
            a, _ = sf.read(os.path.join(work, f"{clip}.wav"), dtype="float32")
            st = int(t / FPS * SR) + int(0.05 * SR)
            track[st:st + len(a)] += a[: max(0, len(track) - st)]
        part = os.path.join(work, f"p{i}.mp4"); tmp = part + ".tmp.mp4"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(work, f"{img}.jpg"),
                            "-vf", f"format=yuv420p,loop=-1:1,trim=duration={dur:.4f}", "-r", str(FPS), "-c:v", "libx264",
                            "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", tmp])
        if r.returncode: fail(f"ffmpeg failed on scene {img}")
        os.replace(tmp, part); lst.append(f"file '{part}'"); t += n
    track = track[: int(total / FPS * SR)]
    track *= 0.89 / max(1e-6, float(np.max(np.abs(track))))
    sf.write(os.path.join(work, "vo.wav"), track, SR)
    open(os.path.join(work, "list.txt"), "w").write("\n".join(lst))
    silent = os.path.join(work, "silent.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(work, "list.txt"), "-c", "copy", silent], check=True)
    tmp = out + ".tmp.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", os.path.join(work, "vo.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-shortest", "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, out)
    return total / FPS


def main():
    if len(sys.argv) != 3: fail("usage: python3 make_video.py spec.json out.mp4")
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    out = os.path.abspath(sys.argv[2])
    check_spec(spec)
    ensure_models()
    work = tempfile.mkdtemp(prefix="udg_video_")
    durs = make_voice(spec, work)
    asyncio.run(shoot(spec, work))
    secs = render(spec, durs, work, out)
    poster = os.path.splitext(out)[0] + "_poster.jpg"
    subprocess.run(["cp", os.path.join(work, "s1_0.jpg"), poster], check=True)
    print(f"built {out}: {secs:.1f} s, {os.path.getsize(out)} bytes; frames in {work}; poster {poster}")


if __name__ == "__main__":
    main()
