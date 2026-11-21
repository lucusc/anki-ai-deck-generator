import unittest

import support
from addon.models.note_payload import NoteMappingError
from addon.services.markup import escape_metadata, sanitize_html


class MarkupTests(unittest.TestCase):
    def test_canonical_safe_formatting_without_attributes_or_urls(self):
        value = '<P style="display:none" onclick="bad()"><B title="secret">A & B</B><br/>2 &lt; 3</P>'
        self.assertEqual(sanitize_html(value), "<p><b>A &amp; B</b><br>2 &lt; 3</p>")
        self.assertEqual(sanitize_html('<table><tr><td colspan="3">x</td></tr></table>'),
                         "<table><tr><td>x</td></tr></table>")
        self.assertEqual(sanitize_html("javascript: text &quot;only&quot;"),
                         "javascript: text &quot;only&quot;")
        self.assertEqual(sanitize_html("<i/>x"), "<i></i>x")

    def test_executable_remote_media_foreign_and_malformed_content_fail(self):
        for value in (
            "<script>secret()</script>", '<img src="https://example.test/x">',
            "<svg><script>x</script></svg>", '<iframe srcdoc="x"></iframe>',
            "<math>x</math>", "<style>.card{display:none}</style>", "<a href='javascript:x'>x</a>",
            "<object>x</object>", "<form>x</form>", "<b><i>x</b></i>", "<b>x",
            "<!--secret--><b>x</b>", "<!DOCTYPE html>x", "<?xml x?>x",
            "<div>" * 33 + "x" + "</div>" * 33, "x" * 32769,
            "x\x00", "x\ud800", "x\x7f",
            "[latex]secret[/latex]", "[$]secret[/$]", "[$$]secret[/$$]",
            "[SOUND:private.mp3]", "&#91;sound:private.mp3]", "[sou<b>nd:</b>private.mp3]",
        ):
            with self.subTest(value=value[:40]), self.assertRaises(NoteMappingError) as error:
                sanitize_html(value)
            self.assertEqual(error.exception.code, "markup")
            self.assertNotIn("secret", str(error.exception))
            self.assertNotIn("private", str(error.exception))

    def test_empty_after_sanitization_is_not_a_success(self):
        for value in ("", " \n\t", "<br>", "<b> </b>"):
            with self.subTest(value=value), self.assertRaises(NoteMappingError):
                sanitize_html(value)
        self.assertEqual(sanitize_html("", allow_empty=True), "")

    def test_cloze_preserves_html_hint_repeat_and_multiple_deletions(self):
        value = "<p>{{c1::<b>cell</b>::structure}} and {{c2::DNA}}; {{c1::membrane}}</p>"
        self.assertEqual(sanitize_html(value, cloze=True), value)
        self.assertEqual(sanitize_html("&#123;&#123;c1::A &amp; B}}", cloze=True),
                         "{{c1::A &amp; B}}")
        self.assertEqual(sanitize_html("{{c99::two\nlines}}", cloze=True),
                         "{{c99::two\nlines}}")

    def test_cloze_missing_malformed_empty_nested_and_cross_tag_deletions_fail(self):
        for value in (
            "no deletion", "{{c0::x}}", "{{c01::x}}", "{{c100::x}}", "{{c-1::x}}",
            "{{c1::}}", "{{c1:: }}", "{{c1::<b></b>}}", "{{c1::x::}}",
            "{{c1::x::a::b}}", "{{c1::outer {{c2::inner}}}}", "{{c1::x}",
            "{{c1::x}} {{c2::broken}", "<b>{{c1::x</b>}}", "{{c1::<b>x}}</b>",
            "{{c1,2::x}}", "{{C1::x}}", '<b title="{{c1::x}}">only attribute</b>',
        ):
            with self.subTest(value=value), self.assertRaises(NoteMappingError) as error:
                sanitize_html(value, cloze=True)
            self.assertEqual(error.exception.code, "cloze")
        with self.assertRaises(NoteMappingError):
            sanitize_html("{{c1::not a basic field}}")

    def test_metadata_cannot_become_html_or_anki_media_or_cloze_syntax(self):
        self.assertEqual(escape_metadata('<x> "[sound:a]" {{c9::x}}'),
                         "&lt;x&gt; &quot;&#91;sound:a&#93;&quot; &#123;&#123;c9::x&#125;&#125;")


if __name__ == "__main__":
    unittest.main()
