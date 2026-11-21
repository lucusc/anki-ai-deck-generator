"""Original, deterministic synthetic PDFs. No downloaded study material."""

import io

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    NumberObject,
)


STUDY_TEXT = (
    "Plants convert sunlight into chemical energy. "
    "Water and carbon dioxide supply the atoms used to make sugars."
)


def text_stream(text: str) -> bytes:
    literal = "".join(
        f"\\{ord(character):03o}"
        if character in "()\\" or not 32 <= ord(character) <= 126
        else character
        for character in text
    )
    return f"BT /F1 12 Tf 72 700 Td ({literal}) Tj ET\n".encode("ascii")


def make_pdf(
    *texts: str,
    image_pages: tuple[int, ...] = (),
    unused_image: bool = False,
    inline_image: bool = False,
    form_image: bool = False,
    compressed: bool = False,
    raw_stream: bytes | None = None,
    form_depth: int = 0,
    form_fanout: int = 2,
    replacement_font: bool = False,
    password: str | None = None,
    encryption_algorithm: str = "RC4-128",
) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    if replacement_font:
        cmap = DecodedStreamObject()
        cmap.set_data(
            b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            b"1 begincodespacerange <00> <FF> endcodespacerange\n"
            b"1 beginbfchar <7F> <FFFD> endbfchar\n"
            b"endcmap CMapName currentdict /CMap defineresource pop end end"
        )
        font[NameObject("/ToUnicode")] = writer._add_object(cmap)
    font_ref = writer._add_object(font)

    def stream(data: bytes) -> DecodedStreamObject:
        result = DecodedStreamObject()
        result.set_data(data)
        return result

    def form(data: bytes, resources: DictionaryObject) -> IndirectObject:
        result = stream(data)
        result.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): ArrayObject([NumberObject(0)] * 2 + [NumberObject(1)] * 2),
                NameObject("/Resources"): resources,
            }
        )
        return writer._add_object(result)

    for number, text in enumerate(texts, start=1):
        page = writer.add_blank_page(width=612, height=792)
        resources = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        data = text_stream(text) if text else b""
        if number in image_pages or unused_image:
            image = stream(b"\x10\x20\x30")
            image.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Image"),
                    NameObject("/Width"): NumberObject(1),
                    NameObject("/Height"): NumberObject(1),
                    NameObject("/BitsPerComponent"): NumberObject(8),
                    NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                }
            )
            image_ref = writer._add_object(image)
            image_resources = DictionaryObject(
                {NameObject("/XObject"): DictionaryObject({NameObject("/Im"): image_ref})}
            )
            if form_image:
                resources[NameObject("/XObject")] = DictionaryObject(
                    {NameObject("/Fm"): form(b"/Im Do\n", image_resources)}
                )
                if number in image_pages:
                    data += b"/Fm Do\n"
            else:
                resources.update(image_resources)
                if number in image_pages:
                    data += b"/Im Do\n"
        if inline_image:
            data += b"BI /W 1 /H 1 /BPC 8 /CS /RGB ID \x10\x20\x30 EI\n"
        if form_depth:
            child = form(b"", DictionaryObject())
            for _ in range(form_depth):
                child = form(
                    b"/Child Do\n" * form_fanout,
                    DictionaryObject(
                        {NameObject("/XObject"): DictionaryObject({NameObject("/Child"): child})}
                    ),
                )
            resources[NameObject("/XObject")] = DictionaryObject(
                {NameObject("/Root"): child}
            )
            data += b"/Root Do\n"
        if raw_stream is not None:
            data = raw_stream
        content = stream(data)
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = writer._add_object(
            content.flate_encode() if compressed else content
        )
    if password is not None:
        writer.encrypt(password, algorithm=encryption_algorithm)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
