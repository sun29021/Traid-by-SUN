"""Descriptive metadata written into exported files.

Only descriptive and ownership fields are supported: title, description, author,
copyright, keywords and comment, plus the Traid edit marker. Capture metadata (camera
make and model, dates taken, GPS location, lens or body serial numbers) is never
written: Traid edits photos, and putting capture data on an edited image would make it
pass as an untouched original (PRD FR-E11, acceptable use).

Formats: JPEG gets EXIF ImageDescription/Artist/Copyright/Software plus the Windows
XP* tags that File Explorer shows (Title, Comment, Author, Keywords) and the marker as
a JPEG comment; PNG gets iTXt chunks with the standard PNG keywords; TIFF gets the
same baseline tags as JPEG. EXIF text tags are 7-bit ASCII, so they get an ASCII
rendering ("(c)" for "©"); the exact Unicode text goes into an XMP packet
(Dublin Core title/description/creator/rights/subject) for JPEG and TIFF.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape

from PIL import Image, PngImagePlugin

# EXIF / TIFF tag numbers.
IMAGE_DESCRIPTION = 270
SOFTWARE = 305
ARTIST = 315
COPYRIGHT = 33432
XP_TITLE = 0x9C9B
XP_COMMENT = 0x9C9C
XP_AUTHOR = 0x9C9D
XP_KEYWORDS = 0x9C9E

# Capture tags that must never be written (checked by tests).
FORBIDDEN_TAGS = frozenset(
    {
        271,  # Make
        272,  # Model
        306,  # DateTime
        0x8769,  # Exif IFD (DateTimeOriginal, body serial, lens …)
        0x8825,  # GPS IFD
        0xA431,  # BodySerialNumber
        0xA435,  # LensSerialNumber
    }
)


@dataclass(frozen=True)
class ImageDetails:
    title: str = ""
    description: str = ""
    author: str = ""
    copyright: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)
    comment: str = ""

    def is_empty(self) -> bool:
        return not any(
            (self.title, self.description, self.author, self.copyright, self.keywords, self.comment)
        )


def _xp(text: str) -> bytes:
    """Windows XP* tags are UTF-16LE with a terminating NUL."""
    return (text + "\0").encode("utf-16-le")


XMP_TAG = 700  # TIFF tag holding an XMP packet
# Typographic characters with a plain-ASCII equivalent (code points, to keep the
# source free of look-alike characters).
_ASCII_SUBSTITUTES = {
    chr(0x00A9): "(c)",  # copyright sign
    chr(0x00AE): "(R)",
    chr(0x2122): "(TM)",
    chr(0x2014): "-",  # em dash
    chr(0x2013): "-",  # en dash
    chr(0x2019): "'",  # curly quotes
    chr(0x2018): "'",
    chr(0x201C): '"',
    chr(0x201D): '"',
}


def ascii_text(text: str) -> str:
    """7-bit rendering for EXIF ASCII fields (accents dropped, © → (c))."""
    for char, substitute in _ASCII_SUBSTITUTES.items():
        text = text.replace(char, substitute)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _baseline_tags(details: ImageDetails, marker: str | None) -> dict[int, Any]:
    tags: dict[int, Any] = {}
    description = details.description or details.title
    if description:
        tags[IMAGE_DESCRIPTION] = ascii_text(description)
    if details.author:
        tags[ARTIST] = ascii_text(details.author)
    if details.copyright:
        tags[COPYRIGHT] = ascii_text(details.copyright)
    if marker:
        tags[SOFTWARE] = ascii_text(marker)
    return tags


def _alt(value: str) -> str:
    return f'<rdf:Alt><rdf:li xml:lang="x-default">{escape(value)}</rdf:li></rdf:Alt>'


def xmp_packet(details: ImageDetails, marker: str | None) -> bytes:
    """Dublin Core fields in UTF-8 (exact text, any language)."""
    fields = []
    if details.title:
        fields.append(f"<dc:title>{_alt(details.title)}</dc:title>")
    if details.description:
        fields.append(f"<dc:description>{_alt(details.description)}</dc:description>")
    if details.author:
        fields.append(
            f"<dc:creator><rdf:Seq><rdf:li>{escape(details.author)}</rdf:li></rdf:Seq></dc:creator>"
        )
    if details.copyright:
        fields.append(f"<dc:rights>{_alt(details.copyright)}</dc:rights>")
    if details.keywords:
        items = "".join(f"<rdf:li>{escape(k)}</rdf:li>" for k in details.keywords)
        fields.append(f"<dc:subject><rdf:Bag>{items}</rdf:Bag></dc:subject>")
    if marker:
        fields.append(f"<xmp:CreatorTool>{escape(marker)}</xmp:CreatorTool>")
    if not fields:
        return b""
    body = "".join(fields)
    packet = (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        f'xmlns:xmp="http://ns.adobe.com/xap/1.0/">{body}</rdf:Description></rdf:RDF></x:xmpmeta>'
        '<?xpacket end="w"?>'
    )
    return packet.encode("utf-8")


def save_options(target: str, details: ImageDetails | None, marker: str | None) -> dict[str, Any]:
    """Extra Pillow `save()` options carrying the metadata for `target` format."""
    details = details or ImageDetails()
    options: dict[str, Any] = {}
    if target == "PNG":
        info = PngImagePlugin.PngInfo()
        for key, value in (
            ("Title", details.title),
            ("Description", details.description),
            ("Author", details.author),
            ("Copyright", details.copyright),
            ("Keywords", "; ".join(details.keywords)),
            ("Comment", details.comment),
            ("Software", marker or ""),
        ):
            if value:
                info.add_itxt(key, value)
        options["pnginfo"] = info
        return options

    tags = _baseline_tags(details, marker)
    if target == "JPEG":
        exif = Image.Exif()
        for tag, value in tags.items():
            exif[tag] = value
        for tag, value in (
            (XP_TITLE, details.title),
            (XP_COMMENT, details.comment),
            (XP_AUTHOR, details.author),
            (XP_KEYWORDS, ";".join(details.keywords)),
        ):
            if value:
                exif[tag] = _xp(value)
        if len(exif):
            options["exif"] = exif.tobytes()
        if marker:
            options["comment"] = marker.encode("utf-8")
        xmp = xmp_packet(details, marker)
        if xmp:
            options["xmp"] = xmp
        return options

    xmp = xmp_packet(details, marker)  # TIFF
    if xmp:
        tags[XMP_TAG] = xmp
    if tags:
        options["tiffinfo"] = tags
    return options
