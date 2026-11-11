"""Crop transparent Fusion screenshots onto white; make the underside close-up."""
import glob
import os
from PIL import Image
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
for f in glob.glob(os.path.join(OUT, "render_*.png")) + glob.glob(os.path.join(OUT, "technic6s_*.png")):
    im = Image.open(f).convert("RGBA")
    if im.getbbox() is None or im.getpixel((0, 0))[3] == 255:
        continue                       # already processed
    im = im.crop(im.getbbox())
    bg = Image.new("RGBA", (im.width + 80, im.height + 80), (255, 255, 255, 255))
    bg.paste(im, (40, 40), im)
    bg.convert("RGB").save(f)
raw = os.path.join(OUT, "_under_raw.png")
if os.path.exists(raw):
    im = Image.open(raw).convert("RGBA")
    im = im.crop(im.getbbox())
    w, h = im.size
    c = im.crop((int(w * 0.28), int(h * 0.18), int(w * 0.75), int(h * 0.80)))
    bg = Image.new("RGBA", c.size, (255, 255, 255, 255))
    bg.paste(c, (0, 0), c)
    bg.convert("RGB").save(os.path.join(OUT, "technic6s_underside_mount_closeup.png"))
    os.remove(raw)
print("images processed")
