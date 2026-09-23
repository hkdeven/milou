"""Tests for editing the sprint tracker, and for the configurable status list.

The tracker is a Word document a person maintains by hand, so most of these
assert that nothing else in it moved: the other sprints, the other lines, the
other files in the zip, and the document's own formatting.
"""


import os
import sys
import unittest
import zipfile
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milou_news import worddoc
from milou_news.actions import (DEFAULT_STATUSES, IncompleteAction, SharePointWordWriter,
                                TicketConfig, WriteNotConfigured, draft_ticket)
from milou_news.worddoc import DocumentError, append_line, append_to_docx, paragraphs

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def heading(text, level=1):
    return ('<w:p><w:pPr><w:pStyle w:val="Heading%d"/></w:pPr>'
            '<w:r><w:t>%s</w:t></w:r></w:p>' % (level, text))


def line(text, style="ListParagraph"):
    return ('<w:p><w:pPr><w:pStyle w:val="%s"/><w:numPr><w:ilvl w:val="0"/>'
            '<w:numId w:val="3"/></w:numPr></w:pPr><w:r><w:t>%s</w:t></w:r></w:p>'
            % (style, text))


DOCUMENT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document %s><w:body>' % W +
            heading("Sprint Ticket Tracker", 1) +
            heading("30 SEP SPRINT", 2) +
            line("1001 - Fix the export") +
            line("1002 - Add the backlog report") +
            heading("7 OCT SPRINT", 2) +
            line("1010 - Rebar slip") +
            '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr>'
            '</w:body></w:document>')


def docx(markup=DOCUMENT, extra=True) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", markup)
        if extra:
            archive.writestr("word/styles.xml", "<styles/>")
            archive.writestr("word/media/image1.png", b"\x89PNG-not-really")
    return buffer.getvalue()


def texts(markup):
    return [item.text for item in paragraphs(markup) if item.text]


class ParsingTest(unittest.TestCase):

    def test_headings_are_told_apart_from_lines(self):
        items = paragraphs(DOCUMENT)
        self.assertTrue(items[1].is_heading)
        self.assertFalse(items[2].is_heading)

    def test_an_empty_paragraph_does_not_break_parsing(self):
        markup = '<w:document %s><w:body><w:p/>%s</w:body></w:document>' % (W, heading("X"))
        self.assertEqual(len(paragraphs(markup)), 2)


class AppendTest(unittest.TestCase):

    def test_the_line_lands_at_the_end_of_its_own_sprint(self):
        updated, detail = append_line(DOCUMENT, "30 SEP SPRINT", "1993 - Issue drawings")
        self.assertIn("added under", detail)
        self.assertEqual(texts(updated), [
            "Sprint Ticket Tracker", "30 SEP SPRINT",
            "1001 - Fix the export", "1002 - Add the backlog report",
            "1993 - Issue drawings",
            "7 OCT SPRINT", "1010 - Rebar slip"])

    def test_nothing_else_in_the_document_changes(self):
        updated, _detail = append_line(DOCUMENT, "30 SEP SPRINT", "1993 - Issue drawings")
        # Everything before the insertion point is byte-identical, and the
        # section properties Word needs at the end survive.
        anchor = DOCUMENT.index("<w:p><w:pPr><w:pStyle w:val=\"Heading2\"/></w:pPr>"
                                "<w:r><w:t>7 OCT SPRINT")
        self.assertTrue(updated.startswith(DOCUMENT[:anchor - 1][:200]))
        self.assertIn("<w:sectPr>", updated)
        self.assertEqual(updated.count("<w:sectPr>"), 1)

    def test_the_new_line_inherits_the_sections_formatting(self):
        updated, _detail = append_line(DOCUMENT, "30 SEP SPRINT", "1993 - Issue drawings")
        added = [item for item in paragraphs(updated)
                 if item.text == "1993 - Issue drawings"][0]
        self.assertIn('w:numId w:val="3"', added.markup,
                      "a tracker line must keep the list numbering around it")
        self.assertEqual(added.style, "ListParagraph")

    def test_an_absent_heading_writes_nothing(self):
        with self.assertRaises(DocumentError) as caught:
            append_line(DOCUMENT, "14 OCT SPRINT", "1993 - Issue drawings")
        self.assertIn("Nothing was written", str(caught.exception))
        self.assertIn("14 OCT SPRINT", str(caught.exception),
                      "name the heading it looked for, so the fix is obvious")

    def test_writing_the_same_line_twice_is_a_no_op(self):
        once, _detail = append_line(DOCUMENT, "30 SEP SPRINT", "1993 - Issue drawings")
        twice, detail = append_line(once, "30 SEP SPRINT", "1993 - Issue drawings")
        self.assertEqual(once, twice)
        self.assertIn("already present", detail)

    def test_an_empty_section_still_accepts_a_line(self):
        markup = ('<w:document %s><w:body>' % W + heading("2 OCT SPRINT", 2) +
                  heading("9 OCT SPRINT", 2) + '</w:body></w:document>')
        updated, _detail = append_line(markup, "2 OCT SPRINT", "1993 - Issue drawings")
        self.assertEqual(texts(updated), ["2 OCT SPRINT", "1993 - Issue drawings",
                                          "9 OCT SPRINT"])

    def test_a_line_added_to_an_empty_section_is_not_itself_a_heading(self):
        markup = ('<w:document %s><w:body>' % W + heading("2 OCT SPRINT", 2) +
                  '</w:body></w:document>')
        updated, _detail = append_line(markup, "2 OCT SPRINT", "1993 - Issue drawings")
        added = [item for item in paragraphs(updated) if item.text == "1993 - Issue drawings"][0]
        self.assertFalse(added.is_heading)

    def test_a_styled_heading_wins_over_a_sentence_that_reads_the_same(self):
        markup = ('<w:document %s><w:body>' % W +
                  line("Everything below is the 30 SEP SPRINT") +
                  heading("30 SEP SPRINT", 2) + line("1001 - Existing") +
                  '</w:body></w:document>')
        updated, _detail = append_line(markup, "30 SEP SPRINT", "1993 - New")
        self.assertEqual(texts(updated)[-1], "1993 - New")

    def test_markup_in_a_title_is_escaped(self):
        updated, _detail = append_line(DOCUMENT, "30 SEP SPRINT", "1993 - Fix <tag> & co")
        self.assertIn("1993 - Fix &lt;tag&gt; &amp; co", updated)
        self.assertIn("1993 - Fix <tag> & co", texts(updated))


class ArchiveTest(unittest.TestCase):

    def test_every_other_file_in_the_docx_is_preserved(self):
        updated, _detail = append_to_docx(docx(), "30 SEP SPRINT", "1993 - Issue drawings")
        before, after = zipfile.ZipFile(BytesIO(docx())), zipfile.ZipFile(BytesIO(updated))
        self.assertEqual(before.namelist(), after.namelist())
        for name in before.namelist():
            if name != worddoc.DOCUMENT_PART:
                self.assertEqual(before.read(name), after.read(name), name)

    def test_the_edited_document_is_still_a_readable_docx(self):
        updated, _detail = append_to_docx(docx(), "30 SEP SPRINT", "1993 - Issue drawings")
        markup = zipfile.ZipFile(BytesIO(updated)).read(worddoc.DOCUMENT_PART).decode("utf-8")
        self.assertIn("1993 - Issue drawings", markup)
        self.assertTrue(markup.startswith("<?xml"))

    def test_a_file_that_is_not_a_docx_is_refused(self):
        with self.assertRaises(DocumentError):
            append_to_docx(b"this is a .doc, not a .docx", "30 SEP SPRINT", "1993 - X")

    def test_a_zip_without_a_document_part_is_refused(self):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/other.xml", "<x/>")
        with self.assertRaises(DocumentError):
            append_to_docx(buffer.getvalue(), "30 SEP SPRINT", "1993 - X")


class SharePointWriterTest(unittest.TestCase):

    def test_a_share_link_is_encoded_the_way_graph_expects(self):
        # u! plus unpadded base64url, per the Graph shares API.
        encoded = SharePointWordWriter.share_id("https://example.test/a b")
        self.assertTrue(encoded.startswith("u!"))
        self.assertNotIn("=", encoded)
        self.assertNotIn("+", encoded)

    def test_without_a_token_nothing_is_fetched(self):
        with self.assertRaises(WriteNotConfigured):
            SharePointWordWriter("https://example.test/x.docx", environ={}) \
                .append_under_heading("doc", "30 SEP SPRINT", "1993 - X")

    def test_without_a_link_nothing_is_fetched(self):
        with self.assertRaises(WriteNotConfigured):
            SharePointWordWriter(token="t").append_under_heading("doc", "30 SEP SPRINT", "1993 - X")

    def test_the_mail_token_cannot_be_used_to_edit_documents(self):
        writer = SharePointWordWriter("https://example.test/x.docx",
                                      environ={"MILOU_OUTLOOK_WRITE_TOKEN": "mail"})
        self.assertIsNone(writer.token)

    def test_a_non_docx_target_is_refused_before_anything_is_written(self):
        writer = _fake_writer(name="Sprint Tracker.doc")
        with self.assertRaises(WriteNotConfigured) as caught:
            writer.append_under_heading("doc", "30 SEP SPRINT", "1993 - X")
        self.assertIn("Save As", str(caught.exception))
        self.assertIn(".docx", str(caught.exception))
        self.assertEqual(writer.calls[-1][0], "GET", "nothing was uploaded")

    def test_the_original_is_backed_up_before_the_upload(self):
        kept = []
        writer = _fake_writer(keep_backup=lambda data, name: kept.append((len(data), name)))
        result = writer.append_under_heading("doc", "30 SEP SPRINT", "1993 - Issue drawings")
        self.assertTrue(result.ok)
        self.assertEqual(len(kept), 1)
        methods = [method for method, _path, _data in writer.calls]
        self.assertEqual(methods[-1], "PUT")

    def test_a_missing_heading_uploads_nothing(self):
        writer = _fake_writer()
        result = writer.append_under_heading("doc", "14 OCT SPRINT", "1993 - X")
        self.assertFalse(result.ok)
        self.assertIn("Nothing was written", result.detail)
        self.assertNotIn("PUT", [method for method, _path, _data in writer.calls])

    def test_a_repeat_run_uploads_nothing(self):
        writer = _fake_writer(content=append_to_docx(docx(), "30 SEP SPRINT", "1993 - X")[0])
        result = writer.append_under_heading("doc", "30 SEP SPRINT", "1993 - X")
        self.assertTrue(result.ok)
        self.assertIn("already present", result.detail)
        self.assertNotIn("PUT", [method for method, _path, _data in writer.calls])


def _fake_writer(name="Sprint Tracker.docx", content=None, keep_backup=None):
    """A writer whose Graph calls are recorded rather than made."""
    import json

    writer = SharePointWordWriter("https://example.test/tracker.docx", token="doc-secret",
                                  keep_backup=keep_backup)
    writer.calls = []
    payload = content if content is not None else docx()

    def request(path, method="GET", data=None, content_type=None):
        writer.calls.append((method, path, data))
        if "/shares/" in path:
            return json.dumps({"id": "item-1", "name": name,
                               "parentReference": {"driveId": "drive-1"}}).encode("utf-8")
        if method == "GET":
            return payload
        return b""

    writer._request = request
    return writer


class StatusListTest(unittest.TestCase):
    """The portal's statuses are configuration; only the default is code."""

    STATUSES = ["Open", "Ready for Development", "In Progress", "In Review", "Released"]

    def test_the_default_is_ready_for_development(self):
        config = TicketConfig.from_mapping({"statuses": self.STATUSES})
        self.assertEqual(config.ready_status, "Ready for Development")
        self.assertEqual(config.statuses, tuple(self.STATUSES))

    def test_the_whole_list_travels_with_the_plan(self):
        config = TicketConfig.from_mapping({"portal": "p", "project": "1",
                                            "statuses": self.STATUSES})
        fields = draft_ticket(config, __import__("datetime").date(2026, 9, 29), subject="X",
                              sender="Marco", body="please add a field").actions[0].fields
        self.assertEqual(fields["status"], "Ready for Development")
        self.assertEqual(fields["status_options"].splitlines(), self.STATUSES)

    def test_a_default_outside_the_list_is_a_configuration_error(self):
        with self.assertRaises(ValueError) as caught:
            TicketConfig.from_mapping({"statuses": ["Open", "Closed"]})
        self.assertIn("Ready for Development", str(caught.exception))

    def test_an_unconfigured_portal_offers_only_the_default(self):
        self.assertEqual(TicketConfig().statuses, DEFAULT_STATUSES)

    def test_a_status_the_portal_does_not_have_cannot_be_approved(self):
        config = TicketConfig.from_mapping({"portal": "p", "project": "1",
                                            "statuses": self.STATUSES})
        plan = draft_ticket(config, __import__("datetime").date(2026, 9, 29), subject="X",
                            sender="Marco", body="please add a field").with_inputs(
                                title="X", status="Ready for QA")
        with self.assertRaises(IncompleteAction) as caught:
            plan.approve("Deven")
        self.assertIn("In Review", str(caught.exception), "the message lists the real options")

    def test_a_status_from_the_list_is_accepted(self):
        config = TicketConfig.from_mapping({"portal": "p", "project": "1",
                                            "statuses": self.STATUSES})
        plan = draft_ticket(config, __import__("datetime").date(2026, 9, 29), subject="X",
                            sender="Marco", body="please add a field").with_inputs(
                                title="X", status="In Progress")
        self.assertTrue(plan.approve("Deven").approved)


if __name__ == "__main__":
    unittest.main()
