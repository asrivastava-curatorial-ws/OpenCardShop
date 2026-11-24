#!/usr/bin/env python3
"""Build assets/starter: the open starter pack, and the application icons.

Downloaded once into --cache (needs internet the first time):
  * Clipart: Microsoft Fluent Emoji, colour style (MIT licence)
      https://github.com/microsoft/fluentui-emoji
  * Fonts: Google Fonts (SIL Open Font Licence 1.1)
      https://github.com/google/fonts
Converting the clipart needs rsvg-convert (Debian/Ubuntu: sudo apt install librsvg2-bin).

Created here, under the project's MIT licence: the backgrounds, the messages and the card
layouts. Re-running replaces assets/starter completely. To add messages without rebuilding,
edit assets/starter/library.json directly.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

os.environ.setdefault("OPENCARDSHOP_NO_SYSTEM_FONTS", "1")  # reproducible font choices
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

FLUENT = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/"
GOOGLE_FONTS = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
DPI = 200  # backgrounds: soft artwork, 200 dpi is ample for print

EMOJI = [
    "Birthday cake", "Balloon", "Wrapped gift", "Party popper", "Partying face", "Cupcake", "Confetti ball",
    "Shortcake", "Soft ice cream", "Revolving hearts", "Red heart", "Rose", "Bouquet", "Clinking glasses",
    "Heart with ribbon", "Love letter", "Wedding", "Ring", "Dove", "Bell", "Baby", "Baby bottle", "Teddy bear",
    "Hatching chick", "Ribbon", "Star", "Trophy", "1st place medal", "Sports medal", "Graduation cap",
    "Clapping hands", "Glowing star", "Crown", "Folded hands", "Sunflower", "Yellow heart", "Hugging face",
    "Smiling face with hearts", "Blossom", "Tulip", "Teacup without handle", "Hot beverage", "Sun with face",
    "Hibiscus", "Herb", "Rainbow", "Diya lamp", "Fireworks", "Sparkler", "Lotus", "Sparkles", "Candy",
    "Artist palette", "Droplet", "Cherry blossom", "Crescent moon", "Mosque", "Christmas tree", "Snowman",
    "Snowflake", "Bottle with popping cork", "Butterfly", "Four leaf clover", "Kite",
    "Smiling face with smiling eyes",
]
FONTS = {  # google/fonts folder -> font file
    "pacifico": "Pacifico-Regular.ttf", "greatvibes": "GreatVibes-Regular.ttf",
    "dancingscript": "DancingScript[wght].ttf", "baloo2": "Baloo2[wght].ttf",
    "playfairdisplay": "PlayfairDisplay[wght].ttf", "lobster": "Lobster-Regular.ttf", "caveat": "Caveat[wght].ttf",
}


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


# --------------------------------------------------------------------------- download
def fetch(url: str, target: Path) -> bool:
    if target.exists() and target.stat().st_size > 0:
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    except OSError:
        return False
    target.write_bytes(data)
    return True


def fetch_sources(cache: Path) -> dict[str, str]:
    found = {}
    for name in EMOJI:
        snake = name.lower().replace(" ", "_").replace("-", "_")
        target = cache / "svg" / f"{snake}.svg"
        for relative in (f"assets/{name}/Color/{snake}_color.svg", f"assets/{name}/Default/Color/{snake}_color_default.svg"):
            if (target.exists() and target.stat().st_size > 200) or fetch(FLUENT + urllib.parse.quote(relative), target):
                found[name] = relative
                break
        else:
            print("  missing clipart:", name)
    fetch(FLUENT + "LICENSE", cache / "FLUENT_LICENSE.txt")
    for folder, file in FONTS.items():
        if not fetch(GOOGLE_FONTS + folder + "/" + urllib.parse.quote(file), cache / "fonts" / file):
            raise SystemExit(f"Cannot download font {file}")
        fetch(GOOGLE_FONTS + folder + "/OFL.txt", cache / "fonts" / f"OFL-{folder}.txt")
    return found


def rasterise(svg: Path, pixels: int) -> Image.Image:
    import io
    data = subprocess.run(["rsvg-convert", "-w", str(pixels), "-h", str(pixels), "-a", str(svg)],
                          check=True, capture_output=True).stdout
    return Image.open(io.BytesIO(data)).convert("RGBA")


# --------------------------------------------------------------------------- backgrounds
def gradient(size, top, bottom):
    line = Image.new("RGB", (1, 256))
    for y in range(256):
        t = y / 255
        line.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return line.resize(size, Image.Resampling.BICUBIC).convert("RGBA")


def hexrgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def border(image, color, inset=0.035, width=0.007, double=False):
    draw = ImageDraw.Draw(image)
    m = round(min(image.size) * inset)
    w = max(2, round(min(image.size) * width))
    radius = round(min(image.size) * 0.03)
    draw.rounded_rectangle((m, m, image.width - m, image.height - m), radius=radius, outline=color, width=w)
    if double:
        m2 = m + w * 3
        draw.rounded_rectangle((m2, m2, image.width - m2, image.height - m2), radius=max(1, radius - w * 2), outline=color, width=max(1, w // 2))


def away_from_centre(rng, size, keep=0.62):
    """A random point outside the central area that holds the card's main content."""
    w, h = size
    while True:
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        if ((x - w / 2) / (w * keep / 2)) ** 2 + ((y - h / 2) / (h * keep / 2)) ** 2 > 1:
            return x, y


def overlay(base, painter):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    painter(ImageDraw.Draw(layer), layer)
    base.alpha_composite(layer)


def confetti(size, top, bottom, colours, seed, edge):
    rng = random.Random(seed)
    image = gradient(size, hexrgb(top), hexrgb(bottom))
    unit = min(size) / 100

    def paint(draw, _):
        for _ in range(110):
            x, y = away_from_centre(rng, size)
            colour = hexrgb(rng.choice(colours)) + (200,)
            if rng.random() < 0.45:
                r = unit * rng.uniform(0.6, 1.3)
                draw.ellipse((x - r, y - r, x + r, y + r), fill=colour)
            else:
                a, length, thick = rng.uniform(0, math.pi), unit * rng.uniform(1.6, 2.8), unit * 0.7
                dx, dy, nx, ny = math.cos(a) * length, math.sin(a) * length, -math.sin(a) * thick, math.cos(a) * thick
                draw.polygon([(x - dx - nx, y - dy - ny), (x + dx - nx, y + dy - ny), (x + dx + nx, y + dy + ny), (x - dx + nx, y - dy + ny)], fill=colour)
    overlay(image, paint)
    border(image, hexrgb(edge) + (255,))
    return image


def heart(cx, cy, scale):
    return [(cx + scale * 16 * math.sin(t) ** 3 / 17, cy - scale * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)) / 17)
            for t in (i * 2 * math.pi / 60 for i in range(60))]


def hearts(size, top, bottom, colours, seed, edge, outline=False, double=False):
    rng = random.Random(seed)
    image = gradient(size, hexrgb(top), hexrgb(bottom))
    unit = min(size) / 100

    def paint(draw, _):
        for _ in range(42):
            x, y = away_from_centre(rng, size, 0.66)
            colour = hexrgb(rng.choice(colours)) + (150 if outline else 120,)
            points = heart(x, y, unit * rng.uniform(1.8, 3.6))
            if outline:
                draw.line(points + points[:1], fill=colour, width=max(2, round(unit * 0.35)))
            else:
                draw.polygon(points, fill=colour)
    overlay(image, paint)
    border(image, hexrgb(edge) + (255,), double=double)
    return image


def rangoli(size, seed):
    rng = random.Random(seed)
    image = gradient(size, hexrgb("#fff3d9"), hexrgb("#ffd59a"))
    unit = min(size) / 100
    palette = ["#e8553e", "#c2185b", "#f4a300", "#7b1fa2", "#2e7d32"]

    def mandala(draw, cx, cy, radius):
        for ring, petals in ((1.0, 16), (0.72, 12), (0.46, 8)):
            colour = hexrgb(rng.choice(palette)) + (210,)
            r = radius * ring
            for k in range(petals):
                a = 2 * math.pi * k / petals
                px, py = cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62
                w = r * math.pi / petals * 0.95
                tip = (cx + math.cos(a) * r, cy + math.sin(a) * r)
                left = (px + math.cos(a + math.pi / 2) * w, py + math.sin(a + math.pi / 2) * w)
                right = (px + math.cos(a - math.pi / 2) * w, py + math.sin(a - math.pi / 2) * w)
                base = (cx + math.cos(a) * r * 0.3, cy + math.sin(a) * r * 0.3)
                draw.polygon([base, left, tip, right], fill=colour)
        for k in range(24):
            a = 2 * math.pi * k / 24
            x, y, d = cx + math.cos(a) * radius * 1.12, cy + math.sin(a) * radius * 1.12, unit * 0.7
            draw.ellipse((x - d, y - d, x + d, y + d), fill=hexrgb("#b71c1c") + (220,))
        d = radius * 0.22
        draw.ellipse((cx - d, cy - d, cx + d, cy + d), fill=hexrgb("#f9a825") + (255,))

    def paint(draw, _):
        radius = min(size) * 0.2
        for cx, cy in ((0, 0), (size[0], 0), (0, size[1]), (size[0], size[1])):
            mandala(draw, cx, cy, radius)
    overlay(image, paint)
    border(image, hexrgb("#b5332e") + (255,))
    return image


def night(size, seed, top="#1d0f45", bottom="#3a1d6b", sparkle="#ffd76a", snow=False):
    rng = random.Random(seed)
    image = gradient(size, hexrgb(top), hexrgb(bottom))
    unit = min(size) / 100

    def paint(draw, _):
        for _ in range(160 if snow else 120):
            x, y = rng.uniform(0, size[0]), rng.uniform(0, size[1])
            r = unit * rng.uniform(0.15, 0.6 if snow else 0.45)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=hexrgb("#ffffff" if snow else sparkle) + (rng.randint(120, 230),))
        if snow:
            for i in range(9):
                cx = size[0] * (i / 8)
                r = unit * rng.uniform(9, 16)
                draw.ellipse((cx - r * 1.6, size[1] - r * 0.7, cx + r * 1.6, size[1] + r * 1.3), fill=(255, 255, 255, 235))
        else:
            for _ in range(9):
                x, y = away_from_centre(rng, size, 0.7)
                r = unit * rng.uniform(1.2, 2.2)
                draw.line((x - r, y, x + r, y), fill=hexrgb(sparkle) + (230,), width=max(2, round(unit * 0.25)))
                draw.line((x, y - r, x, y + r), fill=hexrgb(sparkle) + (230,), width=max(2, round(unit * 0.25)))
    overlay(image, paint)
    border(image, hexrgb(sparkle if not snow else "#cfe3ff") + (255,))
    return image


def splash(size, seed):
    rng = random.Random(seed)
    image = gradient(size, hexrgb("#fffdf8"), hexrgb("#fff6ec"))
    blobs = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(blobs)
    unit = min(size) / 100
    colours = ["#ff4fa3", "#ffd23f", "#3bceac", "#5b8cff", "#a05cff", "#ff7b39"]
    for _ in range(14):
        x, y = away_from_centre(rng, size, 0.72)
        r = unit * rng.uniform(9, 17)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=hexrgb(rng.choice(colours)) + (115,))
    blobs = blobs.filter(ImageFilter.GaussianBlur(unit * 4))
    image.alpha_composite(blobs)

    def paint(draw, _):
        for _ in range(70):
            x, y = away_from_centre(rng, size, 0.68)
            r = unit * rng.uniform(0.3, 1.0)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=hexrgb(rng.choice(colours)) + (210,))
    overlay(image, paint)
    border(image, hexrgb("#d6336c") + (255,))
    return image


def star_points(cx, cy, outer, inner):
    return [(cx + math.cos(-math.pi / 2 + k * math.pi / 5) * (outer if k % 2 == 0 else inner),
             cy + math.sin(-math.pi / 2 + k * math.pi / 5) * (outer if k % 2 == 0 else inner)) for k in range(10)]


def stars(size, seed):
    rng = random.Random(seed)
    image = gradient(size, hexrgb("#0b4552"), hexrgb("#14727c"))
    unit = min(size) / 100

    def paint(draw, _):
        for _ in range(48):
            x, y = away_from_centre(rng, size, 0.7)
            r = unit * rng.uniform(0.7, 1.7)
            draw.polygon(star_points(x, y, r, r * 0.45), fill=hexrgb("#ffd98a") + (rng.randint(150, 235),))
    overlay(image, paint)
    border(image, hexrgb("#e9c46a") + (255,), double=True)
    return image


def meadow(size, seed):
    rng = random.Random(seed)
    image = gradient(size, hexrgb("#f3fbf5"), hexrgb("#d5f0de"))
    unit = min(size) / 100

    def paint(draw, _):
        for _ in range(60):
            x, y = away_from_centre(rng, size, 0.7)
            a, length, width = rng.uniform(0, math.pi), unit * rng.uniform(2, 3.5), unit * rng.uniform(0.8, 1.3)
            points = [(x + math.cos(a) * length * math.cos(t) - math.sin(a) * width * math.sin(t),
                       y + math.sin(a) * length * math.cos(t) + math.cos(a) * width * math.sin(t)) for t in (i * math.pi / 12 for i in range(24))]
            draw.polygon(points, fill=hexrgb(rng.choice(["#7cc49a", "#5aa877", "#a8d8b9", "#f2c14e"])) + (150,))
    overlay(image, paint)
    border(image, hexrgb("#4f9a6e") + (255,))
    return image


def sunny(size, seed):
    image = gradient(size, hexrgb("#fffaf0"), hexrgb("#ffeec4"))
    unit = min(size) / 100

    def paint(draw, _):
        cx, cy = size[0] * 0.96, size[1] * 0.04
        for k in range(18):
            a = math.pi / 2 + k * (math.pi / 2) / 17
            spread = 0.035
            far = max(size) * 0.75
            draw.polygon([(cx, cy), (cx + math.cos(a - spread) * far, cy + math.sin(a - spread) * far),
                          (cx + math.cos(a + spread) * far, cy + math.sin(a + spread) * far)], fill=(255, 214, 102, 55))
        r = unit * 9
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 205, 80, 200))
    overlay(image, paint)
    border(image, hexrgb("#e0a22b") + (255,))
    return image


def sky(size, seed):
    rng = random.Random(seed)
    image = gradient(size, hexrgb("#eef7ff"), hexrgb("#d3e9fb"))
    unit = min(size) / 100

    def paint(draw, _):
        for _ in range(6):
            x, y = away_from_centre(rng, size, 0.75)
            for _ in range(5):
                dx, dy, r = rng.uniform(-6, 6) * unit, rng.uniform(-2, 2) * unit, rng.uniform(3, 5.5) * unit
                draw.ellipse((x + dx - r, y + dy - r, x + dx + r, y + dy + r), fill=(255, 255, 255, 230))
        for _ in range(26):
            x, y = away_from_centre(rng, size, 0.7)
            r = unit * rng.uniform(0.6, 1.2)
            draw.polygon(star_points(x, y, r, r * 0.45), fill=hexrgb("#ffe08a") + (200,))
    overlay(image, paint)
    border(image, hexrgb("#7fb2e5") + (255,))
    return image


def certificate(size):
    image = gradient(size, hexrgb("#fffaf0"), hexrgb("#fbf1d9"))
    gold = hexrgb("#b8913a") + (255,)
    border(image, gold, inset=0.03, width=0.012, double=True)
    draw = ImageDraw.Draw(image)
    unit = min(size) / 100
    m = min(size) * 0.03
    for cx, cy in ((m, m), (size[0] - m, m), (m, size[1] - m), (size[0] - m, size[1] - m)):
        r = unit * 3.2
        draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=gold)
        r2 = unit * 1.3
        draw.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), fill=hexrgb("#fffaf0") + (255,))
    return image


PORTRAIT, LANDSCAPE, FULL = (850, 1100), (1100, 850), (1700, 2200)
BACKGROUNDS = {
    "confetti-peach": lambda s: confetti(s, "#fff4ec", "#ffe0cc", ["#ff6b6b", "#ffb347", "#4ecdc4", "#a78bfa", "#ffd23f"], 1, "#f08a6c"),
    "confetti-mint": lambda s: confetti(s, "#effbf6", "#d2f2e4", ["#2ec4b6", "#ff9f1c", "#e71d36", "#6a4c93", "#ffbf69"], 2, "#3aa58a"),
    "confetti-gold": lambda s: confetti(s, "#fffbea", "#fff0bf", ["#f4a300", "#e63946", "#457b9d", "#2a9d8f", "#c77dff"], 3, "#d4a017"),
    "confetti-sky": lambda s: confetti(s, "#eef6ff", "#d8eaff", ["#4d96ff", "#6bcb77", "#ffd93d", "#ff6b6b", "#b983ff"], 4, "#5b8fd6"),
    "hearts-blush": lambda s: hearts(s, "#fff1f3", "#ffd6de", ["#ff8fa3", "#ff4d6d", "#ffb3c1"], 5, "#e05a78"),
    "hearts-ivory": lambda s: hearts(s, "#fffdf6", "#f6edd6", ["#c9a227", "#e0b84f", "#b8913a"], 6, "#b8913a", outline=True, double=True),
    "sky-baby": lambda s: sky(s, 7),
    "meadow-mint": lambda s: meadow(s, 8),
    "sunny-cream": lambda s: sunny(s, 9),
    "rangoli-saffron": lambda s: rangoli(s, 10),
    "night-festive": lambda s: night(s, 11),
    "snow-night": lambda s: night(s, 12, "#0e2a4a", "#1e4f7c", snow=True),
    "colour-splash": lambda s: splash(s, 13),
    "teal-stars": lambda s: stars(s, 14),
}


# --------------------------------------------------------------------------- messages
def m(front="", inside="", back=""):
    return {k: v for k, v in (("front", front), ("inside", inside), ("back", back)) if v}


BACKS = [m(back="Made with love for <receiver>\nby <sender>"), m(back="A card from <sender>"),
         m(back="Created with OpenCardShop")]
MESSAGES = {
    "birthday": [
        m("Happy Birthday, <receiver>!", "Wishing you a year full of laughter, good friends and plenty of cake."),
        m("Another trip around the sun!", "May this one be your brightest yet. Happy Birthday!"),
        m("Make a wish…", "…and may every one of them come true. Happy Birthday, <receiver>!"),
        m("Today is all about you.", "Celebrate big, laugh often and enjoy every moment.\nWith love, <sender>"),
        m("Cake? Check. Balloons? Check.", "The birthday star? That's you, <receiver>! Have a fantastic day."),
        m("Happy ____ Birthday!", "Here's to many more years of adventures together.\nLove, <sender>"),
        m("Wishing you sunshine", "on your birthday and every day after. Happy Birthday!"),
        m("You're not getting older…", "…you're getting more interesting! Happy Birthday, <receiver>."),
        m("Happy Birthday to a wonderful friend", "Thank you for making every year brighter.\nLove, <sender>"),
        m("Happy Belated Birthday!", "The wishes are late, but they're full of warmth. Hope it was a great day, <receiver>!"),
    ],
    "anniversary": [
        m("Happy Anniversary", "To many more years of love, laughter and holding hands.\nLove, <sender>"),
        m("Together is a wonderful place to be.", "Happy Anniversary, <receiver>!"),
        m("Here's to us", "Every year with you is my favourite. Happy Anniversary.\nLove, <sender>"),
        m("Happy ____ Anniversary!", "Wishing you both a day as special as your love."),
        m("Two hearts, one wonderful journey", "Congratulations on another beautiful year together."),
        m("Still my favourite person", "after all these years. Happy Anniversary, <receiver>."),
        m("Celebrating your love today", "May the years ahead be filled with joy and companionship."),
        m("Cheers to you both!", "Happy Anniversary from <sender>."),
    ],
    "wedding": [
        m("Wedding Wishes", "May your life together be filled with love, laughter and happily ever after."),
        m("Congratulations on your wedding day!", "Wishing you a lifetime of love and happiness.\nWith love, <sender>"),
        m("Two hearts, one home", "May your new journey together be beautiful in every way."),
        m("Best wishes to the happy couple", "Here's to love, adventure and a lifetime of shared dreams."),
        m("Today begins forever", "Congratulations, <receiver>! We are so happy for you."),
        m("Shubh Vivah", "Heartiest congratulations and blessings for a joyful married life.\n<sender>"),
        m("Love is in the air!", "Wishing you both every happiness on your wedding day."),
        m("Thank you for sharing your special day with us", "With love and best wishes,\n<sender>"),
    ],
    "baby": [
        m("Welcome, little one!", "Congratulations on your beautiful new arrival. Wishing your family every joy."),
        m("A tiny miracle has arrived", "Sending love and warm wishes to you all.\n<sender>"),
        m("It's a boy!", "Congratulations! May your little one grow up surrounded by love."),
        m("It's a girl!", "Congratulations! Wishing her a lifetime of happiness."),
        m("Hello, world!", "Welcome to the family, little one.\nWith love, <sender>"),
        m("Ten tiny fingers, ten tiny toes", "and a whole lot of love. Congratulations, <receiver>!"),
        m("Congratulations on your new baby", "Rest when you can, and enjoy every cuddle."),
        m("Happy First Birthday, little one!", "What a wonderful first year.\nLove, <sender>"),
    ],
    "congratulations": [
        m("Congratulations!", "You worked hard for this and you deserve every bit of it. Well done, <receiver>!"),
        m("Well done!", "We are so proud of you.\n<sender>"),
        m("You did it!", "Here's to your success and all the great things still to come."),
        m("Congratulations, graduate!", "The future is bright. Go and make it yours."),
        m("Congratulations on your new job", "They're lucky to have you. Wishing you every success."),
        m("Congratulations on your new home", "May it be filled with happiness, good friends and good food."),
        m("Hats off to you!", "What an achievement. Congratulations, <receiver>!"),
        m("Dream big. Work hard. Shine bright.", "And you did! Congratulations from <sender>."),
    ],
    "thanks": [
        m("Thank You", "Your kindness means more than words can say.\nWith gratitude, <sender>"),
        m("Thank you for everything", "I am so grateful to have you in my life."),
        m("Thanks a million!", "You made a real difference, <receiver>."),
        m("Thank you, Teacher", "for your patience, encouragement and inspiration.\n<sender>"),
        m("Thank you for the lovely gift", "It was so thoughtful of you.\nWith love, <sender>"),
        m("Grateful for you", "Thank you for always being there."),
        m("Thank you for your help", "I couldn't have done it without you."),
        m("A big thank-you", "from all of us.\n<sender>"),
    ],
    "getwell": [
        m("Get well soon", "Sending you warm wishes for a speedy recovery.\n<sender>"),
        m("Thinking of you", "Rest well, take care and feel better soon, <receiver>."),
        m("Wishing you sunshine", "and a quick recovery. We miss you!"),
        m("Feel better soon!", "Here's a little cheer to brighten your day."),
        m("Rest, relax, recover", "and know that we're all thinking of you."),
        m("Sending get-well hugs", "Hope you're back on your feet in no time.\nLove, <sender>"),
        m("Take it easy", "Your only job right now is to get better."),
        m("Hope you're feeling better every day", "With love and best wishes,\n<sender>"),
    ],
    "diwali": [
        m("Shubh Deepavali", "May the festival of lights bring joy, prosperity and peace to your home.\n<sender>"),
        m("Happy Diwali, <receiver>!", "Wishing you a sparkling Diwali and a bright year ahead."),
        m("May the lamps of Diwali", "light up your life with happiness and good health."),
        m("Festival of Lights", "Warm wishes to you and your family this Diwali.\nWith love, <sender>"),
        m("Diyas, rangoli and sweets", "Wishing you a Diwali full of light and laughter."),
        m("Let's light up the night!", "A happy and safe Diwali to you and your loved ones."),
        m("Wishing you a prosperous New Year", "Happy Diwali and Saal Mubarak!"),
        m("May light triumph over darkness", "Happy Deepavali to you all.\n<sender>"),
    ],
    "holi": [
        m("Happy Holi!", "May your life be filled with all the colours of joy.\n<sender>"),
        m("Let the colours fly!", "Wishing you a bright and happy Holi, <receiver>."),
        m("Bura na mano, Holi hai!", "Have a colourful, fun and safe Holi."),
        m("Colours, gujiya and good friends", "Here's to a wonderful Holi together."),
        m("A splash of colour, a splash of joy", "Happy Holi to you and your family."),
        m("May this Holi", "paint your life with happiness, love and laughter."),
        m("Happy Holi from all of us", "With love, <sender>"),
    ],
    "eid": [
        m("Eid Mubarak", "May this blessed day bring peace, happiness and prosperity to you and your family.\n<sender>"),
        m("Eid Mubarak, <receiver>!", "Wishing you joy, love and many blessings."),
        m("Warm wishes on Eid", "May your home be filled with laughter and togetherness."),
        m("Eid al-Fitr Mubarak", "May your prayers be answered and your heart be full."),
        m("Eid al-Adha Mubarak", "Wishing you and your loved ones a joyful and blessed Eid."),
        m("Under the crescent moon", "warmest wishes for a wonderful Eid.\nWith love, <sender>"),
        m("Sweet wishes for Eid", "Enjoy the feast and the company of family and friends."),
    ],
    "christmas": [
        m("Merry Christmas", "Wishing you peace, joy and all the warmth of the season.\n<sender>"),
        m("Merry Christmas, <receiver>!", "May your holidays sparkle with joy and laughter."),
        m("Season's Greetings", "Warm wishes for a happy holiday season and a wonderful New Year."),
        m("Let it snow!", "Have a cosy, merry Christmas.\nLove, <sender>"),
        m("Joy to the world", "and especially to you and your family this Christmas."),
        m("Merry Christmas and a Happy New Year", "With love from all of us,\n<sender>"),
        m("Ho ho ho!", "Hope you get everything on your list."),
        m("Peace, love and joy", "this Christmas and always."),
    ],
    "newyear": [
        m("Happy New Year!", "Wishing you health, happiness and success in the year ahead.\n<sender>"),
        m("Cheers to a new year", "and another chance to get it right! Happy New Year, <receiver>."),
        m("New year, new adventures", "May all your dreams come true this year."),
        m("Out with the old, in with the new", "Here's to a fantastic year ahead."),
        m("Happy ____!", "May the coming year be your best one yet."),
        m("Countdown to happiness", "Wishing you a joyful New Year, <receiver>!"),
        m("Happy New Year from all of us", "With love, <sender>"),
    ],
    "anyday": [
        m("Thinking of you", "and sending a little sunshine your way.\n<sender>"),
        m("Hello, friend!", "Just a note to say you make my world brighter."),
        m("You've got this!", "Believe in yourself. I believe in you, <receiver>."),
        m("Good luck!", "Wishing you all the best. You'll be brilliant."),
        m("Missing you", "Can't wait to see you again.\nLove, <sender>"),
        m("Sorry", "I hope you can forgive me. You mean a lot to me."),
        m("Welcome!", "We're so glad you're here, <receiver>."),
        m("Bon voyage!", "Safe travels, and come back with lots of stories."),
        m("Just because", "You're wonderful, and I wanted you to know."),
    ],
    "awards": [
        m("Certificate of Appreciation\nThis certificate is presented to <receiver>\nfor outstanding effort and achievement"),
        m("Young Scientist Award\npresented to <receiver>\nfor curiosity, careful observation and great questions"),
        m("Star of the Week\n<receiver>\nfor kindness, hard work and a great attitude"),
        m("Certificate of Participation\nawarded to <receiver>"),
        m("Volunteer of the Year\npresented to <receiver>\nwith thanks for your generous time and energy"),
        m("Certificate of Achievement\nawarded to <receiver>\nfor successfully completing ____"),
    ],
}
OCCASIONS = [  # id, label, clipart, backgrounds
    ("birthday", "Birthday", ["Birthday cake", "Balloon", "Wrapped gift", "Party popper", "Partying face", "Cupcake", "Confetti ball", "Shortcake", "Soft ice cream"], ["confetti-peach", "confetti-mint"]),
    ("anniversary", "Anniversary", ["Revolving hearts", "Red heart", "Rose", "Bouquet", "Clinking glasses", "Heart with ribbon", "Love letter"], ["hearts-blush"]),
    ("wedding", "Wedding", ["Wedding", "Ring", "Dove", "Bell", "Bouquet", "Revolving hearts", "Rose", "Clinking glasses"], ["hearts-ivory", "hearts-blush"]),
    ("baby", "New baby", ["Baby", "Baby bottle", "Teddy bear", "Hatching chick", "Ribbon", "Star", "Balloon"], ["sky-baby"]),
    ("congratulations", "Congratulations", ["Trophy", "1st place medal", "Sports medal", "Graduation cap", "Clapping hands", "Party popper", "Glowing star", "Crown", "Confetti ball"], ["confetti-gold"]),
    ("thanks", "Thank you", ["Folded hands", "Bouquet", "Sunflower", "Yellow heart", "Hugging face", "Smiling face with hearts", "Blossom", "Love letter"], ["meadow-mint", "sunny-cream"]),
    ("getwell", "Get well", ["Tulip", "Teacup without handle", "Hot beverage", "Sun with face", "Teddy bear", "Hibiscus", "Herb", "Rainbow"], ["sunny-cream", "meadow-mint"]),
    ("diwali", "Diwali", ["Diya lamp", "Fireworks", "Sparkler", "Lotus", "Sparkles", "Candy", "Glowing star"], ["rangoli-saffron", "night-festive"]),
    ("holi", "Holi", ["Artist palette", "Rainbow", "Droplet", "Cherry blossom", "Hibiscus", "Blossom", "Partying face"], ["colour-splash"]),
    ("eid", "Eid", ["Crescent moon", "Star", "Glowing star", "Mosque", "Sparkles", "Candy"], ["teal-stars"]),
    ("christmas", "Christmas", ["Christmas tree", "Snowman", "Snowflake", "Bell", "Wrapped gift", "Star", "Sparkles"], ["snow-night"]),
    ("newyear", "New Year", ["Fireworks", "Sparkler", "Bottle with popping cork", "Clinking glasses", "Confetti ball", "Party popper", "Sparkles"], ["night-festive", "confetti-sky"]),
    ("anyday", "Any day", ["Sunflower", "Butterfly", "Rainbow", "Four leaf clover", "Kite", "Smiling face with smiling eyes", "Hugging face", "Sun with face", "Love letter", "Herb"], ["meadow-mint", "sunny-cream", "confetti-sky"]),
    ("awards", "Awards & certificates", ["Trophy", "1st place medal", "Sports medal", "Crown", "Glowing star", "Graduation cap", "Star"], []),
]


# --------------------------------------------------------------------------- cards
def strip_fonts(path: Path) -> None:
    """Remove embedded fonts from a starter card; they are resolved from assets/starter/fonts."""
    from zipfile import ZipFile, ZIP_DEFLATED
    with ZipFile(path) as source:
        meta = json.loads(source.read("document.json"))
        meta["font_resources"] = {}
        kept = {name: source.read(name) for name in source.namelist() if name.startswith("images/")}
    with ZipFile(path, "w", ZIP_DEFLATED) as target:
        target.writestr("document.json", json.dumps(meta, ensure_ascii=False, indent=2))
        for name, data in kept.items():
            target.writestr(name, data)


def build_cards(out: Path):
    from opencardshop.assets import AssetStore
    from opencardshop.model import CardDocument, CardObject, save_document
    from opencardshop.render import render_panel

    def art(name, cx, cy, size):
        return CardObject("art", cx - size / 2, cy - size / 2, size, size, art="starter/" + slug(name) + ".webp")

    def bg(name, w, h, kind):
        return CardObject("art", 0, 0, w, h, art=f"starter/bg-{name}-{kind}.webp")

    def text(value, x, y, w, h, font, size, colour, align="center"):
        return CardObject("text", x, y, w, h, text=value, font=font, size=size, color=colour, align=align)

    def back_panel(doc, w, h, picture, imprint="Made with love for <receiver>\nby <sender>"):
        doc.panels["back"] += [art(picture, w / 2, h * 0.52, 800),
                               text(imprint, w * 0.12, h * 0.64, w * 0.76, 700, "Caveat", 18, "#55606b"),
                               text("Made with OpenCardShop", w * 0.15, h - 600, w * 0.7, 300, "Playfair Display", 8, "#8a96a0")]

    def side(file, title, theme, front, inside_art, message, signature, back_art, script="Dancing Script"):
        doc = CardDocument(title=title, fold="side")
        doc.panels["front"] = [bg(theme, 4250, 5500, "portrait")] + front
        doc.panels["inside"] = [art(inside_art, 2125, 2600, 1500),
                                text(message, 4650, 1300, 3450, 2300, "Playfair Display", 21, "#2b3440"),
                                text(signature, 4650, 3800, 3450, 1000, script, 28, "#2b3440")]
        back_panel(doc, 4250, 5500, back_art)
        return file, doc

    def top(file, title, theme, front, inside_art, message, signature, back_art, script="Dancing Script"):
        doc = CardDocument(title=title, fold="top")
        doc.panels["front"] = [bg(theme, 5500, 4250, "landscape")] + front
        doc.panels["inside"] = [art(inside_art, 2750, 2100, 1700),
                                text(message, 700, 4800, 4100, 1900, "Playfair Display", 21, "#2b3440"),
                                text(signature, 700, 6900, 4100, 900, script, 28, "#2b3440")]
        back_panel(doc, 5500, 4250, back_art)
        return file, doc

    def full(file, title, lines, picture):
        doc = CardDocument(title=title, fold="full")
        heading, kind, intro, award = lines
        doc.panels["front"] = [
            bg("certificate-gold", 8500, 11000, "page"),
            text(heading, 800, 1250, 6900, 1600, "Great Vibes", 74, "#8a6d3b"),
            text(kind, 800, 2750, 6900, 700, "Playfair Display", 28, "#5b4a2e"),
            text(intro, 800, 3750, 6900, 600, "Playfair Display", 22, "#444b55"),
            text("<receiver>", 800, 4350, 6900, 1300, "Great Vibes", 60, "#2c3e66"),
            text(award, 900, 5750, 6700, 1000, "Playfair Display", 22, "#444b55"),
            art(picture, 4250, 7450, 1900),
            text("______________________\n<sender>", 900, 9050, 3200, 1000, "Playfair Display", 18, "#444b55"),
            text("______________________\nDate", 4400, 9050, 3200, 1000, "Playfair Display", 18, "#444b55"),
        ]
        return file, doc

    W = 4250
    cards = {
        "birthday": [
            side("birthday-balloons.occard", "Birthday balloons", "confetti-peach",
                 [art("Balloon", 850, 1350, 1100), art("Balloon", 3400, 1200, 900), art("Birthday cake", W / 2, 2650, 2000),
                  text("Happy Birthday!", 300, 3800, 3650, 950, "Pacifico", 40, "#d6455d"),
                  text("<receiver>", 350, 4750, 3550, 500, "Baloo 2", 26, "#7a3e2b")],
                 "Party popper", "Wishing you a year full of laughter, good friends and plenty of cake.", "With love,\n<sender>", "Cupcake"),
            top("birthday-party.occard", "Let's celebrate", "confetti-mint",
                [art("Partying face", 1450, 1800, 2000), art("Wrapped gift", 650, 3300, 850), art("Balloon", 2350, 3250, 850),
                 text("Let's celebrate!", 2900, 900, 2250, 1300, "Lobster", 40, "#1f7a5c"),
                 text("Happy Birthday,\n<receiver>", 2900, 2400, 2250, 1100, "Baloo 2", 24, "#2d4a3e")],
                "Confetti ball", "Hope your birthday is as fun and wonderful as you are!", "Cheers,\n<sender>", "Party popper"),
        ],
        "anniversary": [
            side("anniversary-hearts.occard", "Happy Anniversary", "hearts-blush",
                 [text("Happy Anniversary", 300, 650, 3650, 1300, "Great Vibes", 50, "#b03a5b"),
                  art("Revolving hearts", W / 2, 3000, 2000),
                  text("<receiver>", 350, 4550, 3550, 500, "Playfair Display", 22, "#7d2a40")],
                 "Rose", "To many more years of love, laughter and holding hands.", "Love,\n<sender>", "Red heart", "Great Vibes"),
        ],
        "wedding": [
            side("wedding-wishes.occard", "Wedding wishes", "hearts-ivory",
                 [art("Dove", 3150, 1050, 900), text("Wedding Wishes", 300, 1650, 3650, 1200, "Great Vibes", 52, "#8a6d3b"),
                  art("Bouquet", 1500, 3650, 1500), art("Ring", 2900, 3800, 1100),
                  text("<receiver>", 350, 4750, 3550, 450, "Playfair Display", 22, "#6b5530")],
                 "Wedding", "May your life together be filled with love, laughter and happily ever after.", "With love,\n<sender>", "Bell", "Great Vibes"),
        ],
        "baby": [
            side("new-baby.occard", "Welcome, little one", "sky-baby",
                 [text("Welcome,\nlittle one!", 300, 500, 3650, 1500, "Baloo 2", 38, "#3d6fb6"),
                  art("Teddy bear", W / 2, 3000, 1900), art("Baby bottle", 750, 4400, 800), art("Hatching chick", 3500, 4400, 800)],
                 "Baby", "Congratulations on your beautiful new arrival. Wishing your family every joy.", "With love,\n<sender>", "Ribbon"),
        ],
        "congratulations": [
            top("congratulations.occard", "Congratulations", "confetti-gold",
                [art("Trophy", 1500, 2100, 2300), text("Congratulations!", 2800, 900, 2450, 1300, "Lobster", 40, "#a0671c"),
                 text("Well done,\n<receiver>!", 2800, 2350, 2450, 1100, "Baloo 2", 26, "#5c4210")],
                "1st place medal", "You worked hard for this and you deserve every bit of it.", "Proud of you,\n<sender>", "Glowing star"),
        ],
        "thanks": [
            side("thank-you.occard", "Thank you", "meadow-mint",
                 [art("Bouquet", W / 2, 2150, 2300), text("Thank You", 300, 3800, 3650, 1100, "Pacifico", 50, "#2f7d5b"),
                  text("<receiver>", 350, 4850, 3550, 400, "Playfair Display", 20, "#2b5a45")],
                 "Sunflower", "Your kindness means more than words can say.", "With gratitude,\n<sender>", "Folded hands"),
        ],
        "getwell": [
            side("get-well.occard", "Get well soon", "sunny-cream",
                 [art("Sun with face", 3150, 1050, 1100), text("Get well soon", 300, 1750, 3650, 1000, "Pacifico", 42, "#d9662b"),
                  art("Tulip", 1450, 3700, 1700), art("Teacup without handle", 2850, 3950, 1250)],
                 "Hot beverage", "Sending you warm wishes for a speedy recovery. Rest well and take care.", "Thinking of you,\n<sender>", "Herb"),
        ],
        "diwali": [
            side("diwali-diyas.occard", "Shubh Deepavali", "rangoli-saffron",
                 [text("Shubh Deepavali", 300, 700, 3650, 1100, "Lobster", 44, "#8b1e3f"), art("Sparkles", W / 2, 2050, 900),
                  art("Diya lamp", 900, 3200, 1100), art("Diya lamp", W / 2, 3050, 1300), art("Diya lamp", 3350, 3200, 1100),
                  text("Happy Diwali, <receiver>", 350, 4250, 3550, 600, "Playfair Display", 22, "#6b1630")],
                 "Lotus", "May the festival of lights bring joy, prosperity and peace to your home.", "Warm wishes,\n<sender>", "Candy"),
            top("diwali-lights.occard", "Festival of lights", "night-festive",
                [art("Diya lamp", 1450, 2150, 2200), art("Sparkles", 2250, 900, 800),
                 text("Festival of Lights", 2850, 900, 2400, 1400, "Great Vibes", 46, "#ffd76a"),
                 text("Happy Diwali", 2850, 2450, 2400, 800, "Baloo 2", 26, "#ffe9b0"), art("Sparkles", 4050, 3550, 650)],
                "Sparkles", "Wishing you a sparkling Diwali and a bright year ahead.", "With love,\n<sender>", "Diya lamp"),
        ],
        "holi": [
            top("holi-colours.occard", "Happy Holi", "colour-splash",
                [art("Artist palette", 1450, 1900, 2100), text("Happy Holi!", 2800, 900, 2450, 1300, "Pacifico", 48, "#d6336c"),
                 text("Let the colours fly,\n<receiver>!", 2800, 2350, 2450, 1100, "Baloo 2", 22, "#6a3d9a")],
                "Rainbow", "May your life be filled with all the colours of joy.", "Happy Holi,\n<sender>", "Cherry blossom"),
        ],
        "eid": [
            side("eid-mubarak.occard", "Eid Mubarak", "teal-stars",
                 [art("Crescent moon", 2650, 1350, 1500), art("Star", 1350, 1000, 600),
                  text("Eid Mubarak", 300, 2450, 3650, 1300, "Great Vibes", 56, "#ffe3a3"), art("Mosque", W / 2, 4300, 1300)],
                 "Glowing star", "May this blessed day bring peace, happiness and prosperity to you and your family.", "With warm wishes,\n<sender>", "Star"),
        ],
        "christmas": [
            side("christmas-tree.occard", "Merry Christmas", "snow-night",
                 [text("Merry Christmas", 300, 500, 3650, 1100, "Lobster", 46, "#ffffff"), art("Christmas tree", W / 2, 2850, 2100),
                  art("Snowman", 850, 4350, 1000), art("Wrapped gift", 3400, 4450, 800)],
                 "Snowflake", "Wishing you peace, joy and all the warmth of the season.", "Merry Christmas,\n<sender>", "Bell"),
        ],
        "newyear": [
            top("new-year.occard", "Happy New Year", "night-festive",
                [art("Confetti ball", 1450, 1450, 1700), art("Bottle with popping cork", 900, 3150, 1100), art("Clinking glasses", 2050, 3150, 1100),
                 text("Happy New Year!", 2850, 1000, 2400, 1300, "Lobster", 44, "#ffd76a"),
                 text("Cheers to new adventures", 2850, 2450, 2400, 900, "Baloo 2", 22, "#ffe9b0")],
                "Sparkles", "Wishing you health, happiness and success in the year ahead.", "Cheers,\n<sender>", "Party popper"),
        ],
        "anyday": [
            side("thinking-of-you.occard", "Thinking of you", "meadow-mint",
                 [art("Butterfly", 3200, 1000, 900), art("Sunflower", W / 2, 2550, 2100),
                  text("Thinking of you", 300, 3850, 3650, 1000, "Dancing Script", 46, "#b8632a"),
                  text("<receiver>", 350, 4850, 3550, 400, "Playfair Display", 20, "#5a4632")],
                 "Four leaf clover", "Sending a little sunshine your way.", "Love,\n<sender>", "Butterfly"),
            top("hello-friend.occard", "Hello, friend", "confetti-sky",
                [art("Smiling face with smiling eyes", 1450, 1900, 2000), text("Hello, friend!", 2800, 900, 2450, 1300, "Pacifico", 44, "#2f6fb0"),
                 text("You make my world brighter", 2800, 2350, 2450, 1000, "Baloo 2", 22, "#24496b")],
                "Kite", "Just a note to say I'm glad you're my friend.", "Your friend,\n<sender>", "Four leaf clover"),
        ],
        "awards": [
            full("certificate-appreciation.occard", "Certificate of appreciation",
                 ("Certificate", "of Appreciation", "This certificate is proudly presented to", "for outstanding effort and achievement"), "Trophy"),
            full("young-scientist.occard", "Young Scientist Award",
                 ("Young Scientist", "Award", "This award is presented to", "for curiosity, careful observation and great questions"), "Sports medal"),
        ],
    }
    store = AssetStore(Path(tempfile.mkdtemp()) / "no-cd", None, starter=out, personal=False)
    (out / "cards").mkdir(parents=True, exist_ok=True)
    listing = {}
    for occasion, items in cards.items():
        listing[occasion] = []
        for file, doc in items:
            target = out / "cards" / file
            save_document(doc, target, store)
            strip_fonts(target)  # the starter fonts ship with the app; a user's saved copy embeds them
            errors = []
            preview = render_panel(doc, "front", store, width=220 if doc.fold == "top" else 180, errors=errors).convert("RGB")
            if errors:
                raise SystemExit(f"{file}: {errors}")
            preview.save(target.with_suffix(".png"), "PNG", optimize=True)
            listing[occasion].append({"file": file, "title": doc.title, "fold": doc.fold})
    return listing


# --------------------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=ROOT / "assets/starter")
    parser.add_argument("--icons", type=Path, default=ROOT / "assets/icons")
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/opencardshop/starter-sources")
    parser.add_argument("--pixels", type=int, default=768, help="clipart size in pixels")
    args = parser.parse_args()
    if not shutil.which("rsvg-convert"):
        raise SystemExit("rsvg-convert is required (Debian/Ubuntu: sudo apt install librsvg2-bin)")
    print("Fetching sources into", args.cache)
    sources = fetch_sources(args.cache)
    out = args.output
    if out.exists():
        shutil.rmtree(out)
    (out / "art").mkdir(parents=True)
    (out / "fonts").mkdir()
    print("Clipart:", len(sources))
    for name in sources:
        snake = name.lower().replace(" ", "_").replace("-", "_")
        rasterise(args.cache / "svg" / f"{snake}.svg", args.pixels).save(out / "art" / f"{slug(name)}.webp", "WEBP", quality=92, method=6, alpha_quality=100)
    print("Backgrounds:", len(BACKGROUNDS) * 2 + 1)
    for name, painter in BACKGROUNDS.items():
        for kind, size in (("portrait", PORTRAIT), ("landscape", LANDSCAPE)):
            painter(size).convert("RGB").save(out / "art" / f"bg-{name}-{kind}.webp", "WEBP", quality=90, method=6)
    certificate(FULL).convert("RGB").save(out / "art" / "bg-certificate-gold-page.webp", "WEBP", quality=90, method=6)
    for file in sorted((args.cache / "fonts").iterdir()):
        shutil.copy2(file, out / "fonts" / file.name)

    occasions = []
    for key, label, clipart, backgrounds in OCCASIONS:
        art = [f"{slug(n)}.webp" for n in clipart if n in sources]
        art += [f"bg-{b}-{k}.webp" for b in backgrounds for k in ("portrait", "landscape")]
        if key == "awards":
            art.append("bg-certificate-gold-page.webp")
        occasions.append({"id": key, "label": label, "art": art, "cards": [],
                          "messages": MESSAGES[key] + ([] if key == "awards" else BACKS)})
    index = {"format": "OpenCardShop starter library", "version": 1, "occasions": occasions}
    (out / "library.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Cards…")
    listing = build_cards(out)
    for occasion in occasions:
        occasion["cards"] = listing.get(occasion["id"], [])
    (out / "library.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    attribution = ["# Starter pack: sources and licences", "",
                   "Everything in this folder may be redistributed with OpenCardShop.", "",
                   "## Clipart: Microsoft Fluent Emoji (MIT licence)", "",
                   "Colour-style SVGs from https://github.com/microsoft/fluentui-emoji, converted to WebP. "
                   "Copyright (c) Microsoft Corporation. The MIT licence text is in `LICENSE-FluentEmoji.txt`.", ""]
    attribution += [f"- `art/{slug(n)}.webp` ← `{relative}`" for n, relative in sorted(sources.items())]
    attribution += ["", "## Fonts: SIL Open Font Licence 1.1", "",
                    "From https://github.com/google/fonts. Each font's licence is beside it as `fonts/OFL-<family>.txt`.", ""]
    attribution += [f"- `fonts/{file}` (google/fonts `ofl/{folder}`)" for folder, file in FONTS.items()]
    attribution += ["", "## Created for OpenCardShop (MIT licence, like the rest of the project)", "",
                    "- Backgrounds `art/bg-*.webp`, drawn by `tools/build_starter_pack.py`.",
                    "- All messages in `library.json`.",
                    "- Card layouts in `cards/` (they embed the clipart and fonts above, under their own licences).", ""]
    (out / "ATTRIBUTION.md").write_text("\n".join(attribution), encoding="utf-8")
    shutil.copy2(args.cache / "FLUENT_LICENSE.txt", out / "LICENSE-FluentEmoji.txt")

    # Application icon: the Fluent "Love letter" emoji (MIT).
    args.icons.mkdir(parents=True, exist_ok=True)
    icon = rasterise(args.cache / "svg" / "love_letter.svg", 256)
    icon.save(args.icons / "opencardshop.png", "PNG", optimize=True)
    icon.save(args.icons / "opencardshop.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    (args.icons / "README.md").write_text("The application icon is the \"Love letter\" emoji from Microsoft Fluent Emoji "
                                          "(MIT licence, see ../starter/LICENSE-FluentEmoji.txt).\n", encoding="utf-8")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"Starter pack: {len(occasions)} occasions, {sum(len(o['cards']) for o in occasions)} cards, "
          f"{len(list((out / 'art').iterdir()))} pictures, {sum(len(o['messages']) for o in occasions)} messages, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
