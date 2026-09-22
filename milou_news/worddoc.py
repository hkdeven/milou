"""Appending one line to a Word document, without rewriting it.

The sprint tracker is a Word document that a person maintains by hand. That
makes it the most dangerous thing Milou touches: a ticket can be deleted and a
mail can be recalled, but silently mangling a document somebody has been editing
for months is not recoverable from here.

So this module does the least possible. A ``.docx`` is a zip containing
``word/document.xml``, and rather than parsing that XML into a tree and
re-serialising it — which reorders attributes, drops namespace declarations
Word put there for a reason, and rewrites parts nobody asked it to touch — this
works on the raw markup as text and **splices in one paragraph**. Every other
byte of the document, and every other file in the zip, is carried across
unchanged.

The new paragraph is cloned from an existing line in the same section, so it
inherits whatever bullet, indent or numbering that section already uses. If the
heading cannot be found, nothing is written and the caller is told; guessing
where the line goes is worse than not writing it.
"""

import re
import shutil
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Tuple

DOCUMENT_PART = "word/document.xml"

#: One paragraph, including the self-closing form Word emits for empty ones.
_PARAGRAPH = re.compile(r"<w:p(?:\s[^>]*)?/>|<w:p(?:\s[^>]*)?>.*?</w:p>", re.S)
_TEXT = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.S)
_TEXT_OPEN = re.compile(r"<w:t(?:\s[^>]*)?>")
_STYLE = re.compile(r'<w:pStyle\s[^>]*w:val="([^"]+)"')
_HEADING_STYLE = re.compile(r"^(?:Heading|Title|Subtitle)", re.I)


class DocumentError(Exception):
    """Raised when the document cannot be edited safely."""


@dataclass(frozen=True)
class Paragraph:
    start: int
    end: int
    markup: str
    text: str
    style: str

    @property
    def is_heading(self) -> bool:
        return bool(_HEADING_STYLE.match(self.style))


def _unescape(value: str) -> str:
    return (value.replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))


def _escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def paragraphs(markup: str) -> List[Paragraph]:
    found = []
    for match in _PARAGRAPH.finditer(markup):
        block = match.group(0)
        text = " ".join(_unescape("".join(_TEXT.findall(block))).split())
        style = _STYLE.search(block)
        found.append(Paragraph(match.start(), match.end(), block, text,
                               style.group(1) if style else ""))
    return found


def _normalise(value: str) -> str:
    return " ".join((value or "").split()).strip().lower()


def find_heading(items: List[Paragraph], heading: str) -> Optional[int]:
    """The index of the heading paragraph, matched on its text.

    A styled heading wins over a plain paragraph that happens to read the same,
    because a sprint tag can easily appear in a sentence further down.
    """
    wanted = _normalise(heading)
    if not wanted:
        return None
    exact_styled = [index for index, item in enumerate(items)
                    if item.is_heading and _normalise(item.text) == wanted]
    if exact_styled:
        return exact_styled[0]
    exact = [index for index, item in enumerate(items) if _normalise(item.text) == wanted]
    if exact:
        return exact[0]
    contained = [index for index, item in enumerate(items)
                 if item.is_heading and wanted in _normalise(item.text)]
    return contained[0] if contained else None


def _section_end(items: List[Paragraph], start: int) -> int:
    """The index just past the last paragraph belonging to this heading."""
    for index in range(start + 1, len(items)):
        if items[index].is_heading:
            return index
    return len(items)


def _clone(template: Paragraph, line: str) -> str:
    """The template paragraph with its text replaced by ``line``.

    Only the text is replaced. The paragraph properties — numbering, indent,
    style — are exactly the ones the section already uses, which is the whole
    reason for cloning rather than emitting a bare paragraph.
    """
    if not _TEXT.search(template.markup):
        return ("<w:p><w:r><w:t xml:space=\"preserve\">%s</w:t></w:r></w:p>" % _escape(line))
    replaced = {"done": False}

    def swap(match):
        if replaced["done"]:
            return "<w:t></w:t>"
        replaced["done"] = True
        return "<w:t xml:space=\"preserve\">%s</w:t>" % _escape(line)

    return _TEXT.sub(swap, template.markup)


def append_line(markup: str, heading: str, line: str) -> Tuple[str, str]:
    """Insert ``line`` at the end of ``heading``'s section.

    Returns the new markup and a short description of what happened. Raises
    :class:`DocumentError` when the heading is absent: a line filed under the
    wrong sprint is harder to notice than a line that was never written.
    """
    items = paragraphs(markup)
    index = find_heading(items, heading)
    if index is None:
        raise DocumentError(
            "no heading %r in the document; nothing was written" % heading)
    end = _section_end(items, index)
    body = items[index + 1:end]
    if any(_normalise(item.text) == _normalise(line) for item in body):
        return markup, "already present under %r; left unchanged" % heading

    written = [item for item in body if item.text]
    template = written[-1] if written else None
    if template is None:
        # An empty section: clone the heading's own paragraph so the document's
        # own formatting is still the source, then strip the heading style so
        # the line does not become a heading itself.
        template = items[index]
        clone = _clone(template, line)
        clone = _STYLE.sub("", clone)
    else:
        clone = _clone(template, line)

    anchor = items[end - 1] if end > index else items[index]
    return markup[:anchor.end] + clone + markup[anchor.end:], "added under %r" % heading


def append_to_docx(data: bytes, heading: str, line: str) -> Tuple[bytes, str]:
    """Rewrite a ``.docx``, changing only ``word/document.xml``.

    Every other zip entry is copied across byte for byte, in its original order,
    with its original compression. Word is particular about what it finds in
    there, and this is a file somebody else owns.
    """
    try:
        source = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocumentError("this is not a .docx file: %s" % exc)
    if DOCUMENT_PART not in source.namelist():
        raise DocumentError("no %s in the document; is it a .doc rather than a .docx?"
                            % DOCUMENT_PART)
    markup = source.read(DOCUMENT_PART).decode("utf-8")
    updated, detail = append_line(markup, heading, line)
    if updated == markup:
        return data, detail

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for item in source.infolist():
            payload = updated.encode("utf-8") if item.filename == DOCUMENT_PART \
                else source.read(item.filename)
            target.writestr(item, payload, item.compress_type)
    return buffer.getvalue(), detail


def backup(data: bytes, path: str) -> str:
    """Keep the bytes that were there before. Cheap, and once it matters it is
    the only copy of a document somebody spent months on."""
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def copy_file(source_path: str, target_path: str) -> str:
    shutil.copyfile(source_path, target_path)
    return target_path
