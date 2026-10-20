"""Draw packaging/traid.ico: an amber "T" on the dark Traid surface colour."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SIZE = 256


def draw() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image)
    canvas.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=52, fill=(22, 22, 22, 255))
    canvas.rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=52, outline=(242, 179, 61, 255), width=6)
    font = ImageFont.load_default(size=176)
    box = canvas.textbbox((0, 0), "T", font=font)
    x = (SIZE - (box[2] - box[0])) / 2 - box[0]
    y = (SIZE - (box[3] - box[1])) / 2 - box[1]
    canvas.text((x, y), "T", font=font, fill=(242, 179, 61, 255))
    return image


if __name__ == "__main__":
    draw().save(HERE / "traid.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    draw().save(HERE / "traid-icon.png")
    print("icon written")
