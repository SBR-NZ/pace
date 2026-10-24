"""Project overview page checks, against the shipped template and the invented example only.

The template beside the Project overview add-in is the one source of the page.
These checks read the template and the invented example page filled in from
it. They never open an owner's folder.
"""

from datetime import date
from html.entities import html5 as NAMED_ENTITIES
from html.parser import HTMLParser
from pathlib import Path
import html
import importlib.util
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADD_IN_FOLDER = Path("Product/Pace add-ins/Project overview")
TEMPLATE = ROOT / "PACE" / ADD_IN_FOLDER / "overview-template.html"
ADD_IN = ROOT / "PACE" / ADD_IN_FOLDER / "ADD-IN.md"
EXAMPLE = ROOT / "example"
EXAMPLE_PAGE = EXAMPLE / "Views/2026-10-30-project-overview.html"

_spec = importlib.util.spec_from_file_location("pace_record", ROOT / "PACE/Product/Tools/pace_record.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

PRODUCT_NAME = "Pace by Simply Better Reports"
VIEWS = ("every project", "one project", "by person")
FACTS = ("As at", "Asked", "Searched", "Could not read")

# Everything a page may contain. No element or attribute here can run code or fetch anything.
ALLOWED_TAGS = {
    "html", "head", "meta", "title", "style", "body", "main", "header", "footer", "section",
    "article", "div", "h1", "h2", "h3", "p", "dl", "dt", "dd", "ul", "ol", "li", "strong", "span",
}
ALLOWED_ATTRIBUTES = {"lang", "charset", "name", "content", "class"}
VOID = {"meta"}
PHRASING = {"strong", "span"}
HEAD_CHILDREN = {"meta", "title", "style"}
FORBIDDEN = re.compile(
    r"<\s*(?:script|link|img|iframe|frame|object|embed|base|form|input|button|svg|math|video|audio|source|picture)\b"
    r"|\b(?:src|href|srcset|action|style)\s*="
    r"|\bon[a-z]+\s*="
    r"|url\s*\(|@import|@font-face|://|http-equiv|javascript:",
    re.I,
)
TEMPLATE_RULE = re.compile(r"^\s+(\S)\s+with\s+(&#?[a-z0-9]+;)\s*$", re.M)
ADD_IN_RULE = re.compile(r"`(.)` becomes `(&#?[a-z0-9]+;)`")
BAD_AMPERSAND = re.compile(r"&(?!(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#x[0-9A-Fa-f]+);)")
HOSTILE = (
    "<script>alert(1)</script>",
    "<Drivers & Inputs>",
    '"><img src=x onerror=alert(1)>',
    "</p></li></ul><h1>Not from the record</h1>",
    "Tom's \"draft\" & <b>notes</b>",
    "&lt;already escaped&gt; &amp; &#39;",
    "<!-- hidden --> <style>body{display:none}</style>",
    "<a href=\"https://example.invalid\">link</a>",
)


class Page(HTMLParser):
    """A strict reading of one page: every tag closed, nested where HTML allows, and nothing unexpected."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.doctype = None
        self.problems = []
        self.tags = []
        self.comments = []
        self.style = ""
        self.items = []
        self.text = []
        self._stack = []
        self._open_items = []
        self.feed(text)
        self.close()
        if self._stack:
            self.problems.append(f"not closed: {[tag for tag, _ in self._stack]}")

    def classes(self):
        return {name for _, attrs in self.tags for name in attrs.get("class", "").split()}

    def handle_decl(self, decl):
        if self.doctype is not None:
            self.problems.append("more than one doctype")
        self.doctype = decl

    def unknown_decl(self, data):
        self.problems.append(f"unexpected declaration: {data!r}")

    def handle_pi(self, data):
        self.problems.append(f"unexpected processing instruction: {data!r}")

    def handle_comment(self, data):
        self.comments.append(data.strip())

    def _check_place(self, tag):
        parent = self._stack[-1][0] if self._stack else None
        if tag not in ALLOWED_TAGS:
            self.problems.append(f"tag not allowed: {tag}")
        if parent is None and tag != "html":
            self.problems.append(f"{tag} outside html")
        if parent == "head" and tag not in HEAD_CHILDREN:
            self.problems.append(f"{tag} inside head")
        if parent in ("p", "h1", "h2", "h3", "dt", "strong", "span") and tag not in PHRASING:
            self.problems.append(f"{tag} inside {parent}")
        if parent in ("ul", "ol") and tag != "li":
            self.problems.append(f"{tag} directly inside {parent}")
        if parent == "dl" and tag not in ("dt", "dd"):
            self.problems.append(f"{tag} directly inside dl")
        if tag == "li" and parent not in ("ul", "ol"):
            self.problems.append(f"li inside {parent}")
        if tag in ("dt", "dd") and parent != "dl":
            self.problems.append(f"{tag} inside {parent}")

    def _record_tag(self, tag, attrs):
        values = dict(attrs)
        if len(values) != len(attrs):
            self.problems.append(f"repeated attribute on {tag}")
        for name in values:
            if name not in ALLOWED_ATTRIBUTES:
                self.problems.append(f"attribute not allowed: {tag} {name}")
        self.tags.append((tag, values))
        return values

    def handle_starttag(self, tag, attrs):
        self._check_place(tag)
        values = self._record_tag(tag, attrs)
        if tag in VOID:
            return
        self._stack.append((tag, values.get("class", "").split()))
        if tag == "li" and "item" in self._stack[-1][1]:
            self._open_items.append((len(self._stack), []))

    def handle_startendtag(self, tag, attrs):
        self._check_place(tag)
        self._record_tag(tag, attrs)
        if tag not in VOID:
            self.problems.append(f"{tag} written as self-closing")

    def handle_endtag(self, tag):
        if tag in VOID:
            self.problems.append(f"end tag for {tag}")
            return
        if not self._stack or self._stack[-1][0] != tag:
            self.problems.append(f"unexpected end tag: {tag}")
            return
        if self._open_items and self._open_items[-1][0] == len(self._stack):
            _, parts = self._open_items.pop()
            self.items.append(" ".join("".join(parts).split()))
        self._stack.pop()

    def handle_data(self, data):
        if self._stack and self._stack[-1][0] == "style":
            self.style += data
            return
        for _, parts in self._open_items:
            parts.append(data)
        self.text.append(data)


def read(path):
    return path.read_text(encoding="utf-8")


def without_comments_and_style(text):
    return re.sub(r"<style>.*?</style>", "", re.sub(r"<!--.*?-->", "", text, flags=re.S), flags=re.S)


def section(text, heading):
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1)


def template_rules():
    note = re.match(r"<!DOCTYPE html>\n<!--(.*?)-->", read(TEMPLATE), re.S).group(1)
    return TEMPLATE_RULE.findall(note)


def escape(text, rules):
    for raw, entity in rules:
        text = text.replace(raw, entity)
    return text


def first_item_block():
    return re.search(r'<li class="item">.*?</li>', read(TEMPLATE), re.S).group(0)


def views(text):
    found = []
    for view in VIEWS:
        start = text.find(f"<!-- start: {view} view -->")
        end = text.find(f"<!-- end: {view} view -->")
        if start != -1 or end != -1:
            found.append((view, start, end))
    return found


def long_date(day):
    return f"{day.day} {day:%B %Y}"


def short_date(day):
    return f"{day.day} {day:%b %Y}"


class TemplateTests(unittest.TestCase):
    def test_template_is_one_self_contained_file(self):
        text = read(TEMPLATE)
        self.assertIsNone(FORBIDDEN.search(text))
        self.assertNotIn("<script", text.lower())
        page = Page(text)
        self.assertEqual(page.problems, [])
        self.assertEqual(page.doctype, "DOCTYPE html")
        self.assertEqual([tag for tag, _ in page.tags].count("style"), 1)
        # The only files beside the add-in are its instructions, this template and its launcher.
        folder = TEMPLATE.parent
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["ADD-IN.md", "Launchers", "overview-template.html"])

    def test_template_reads_in_light_and_dark_printed_and_on_a_phone(self):
        page = Page(read(TEMPLATE))
        metas = [attrs for tag, attrs in page.tags if tag == "meta"]
        self.assertEqual(metas[0], {"charset": "utf-8"})
        self.assertIn({"name": "viewport", "content": "width=device-width, initial-scale=1"}, metas)
        self.assertIn({"name": "color-scheme", "content": "light dark"}, metas)
        style = page.style
        for media in ("@media (prefers-color-scheme: dark)", "@media print", "@media (max-width: 40rem)"):
            self.assertEqual(style.count(media), 1, media)
        # Every colour is a named setting, and dark mode and print each set every one of them.
        light = re.search(r":root \{(.*?)\}", style, re.S).group(1)
        names = set(re.findall(r"(--[a-z-]+):", light))
        self.assertGreater(len(names), 5)
        for media in ("@media (prefers-color-scheme: dark)", "@media print"):
            block = re.search(rf"{re.escape(media)} \{{\s*:root \{{(.*?)\}}", style, re.S).group(1)
            self.assertEqual(set(re.findall(r"(--[a-z-]+):", block)), names, media)
        for line in style.splitlines():
            if re.search(r"#[0-9a-fA-F]{3,6}\b", line):
                self.assertRegex(line, r"^\s*--[a-z-]+: #[0-9a-f]{6};$")

    def test_template_has_the_three_views_and_the_lines_every_page_needs(self):
        text = read(TEMPLATE)
        found = views(text)
        self.assertEqual([view for view, _, _ in found], list(VIEWS))
        header_end = text.index("</header>")
        footer_start = text.index('<footer class="foot">')
        for view, start, end in found:
            with self.subTest(view=view):
                self.assertTrue(header_end < start < end < footer_start)
                self.assertEqual(text.count(f"<!-- start: {view} view -->"), 1)
        # As at, Asked, Searched and Could not read sit in the shared header, so every view has them.
        header = text[text.index("<header>"):header_end]
        self.assertEqual(re.findall(r"<dt>(.*?)</dt>", header), list(FACTS))
        self.assertIn(f'<p class="product">{PRODUCT_NAME}</p>', header)
        self.assertIn(f"<p>{PRODUCT_NAME}</p>", text[footer_start:])
        self.assertRegex(text, rf"<title>[^<]+ - {PRODUCT_NAME}</title>")
        every = text[found[0][1]:found[0][2]]
        for label in ("Owned by", "Due", "Recorded two ways", "Overdue", "Due soon", "Waiting on you"):
            self.assertIn(label, every)
        self.assertLess(every.index("Overdue"), every.index("Due soon"))
        self.assertLess(every.index("Due soon"), every.index("Waiting on you"))
        one = text[found[1][1]:found[1][2]]
        headings = re.findall(r"<h3>(.*?)</h3>", one)
        self.assertEqual(headings, [
            "Recorded two ways", "Decisions waiting on you", "Open tasks", "Related work", "Notes",
            "Projects inside it", "Documents and repository references", "Done in the last three weeks",
            "Cancelled",
        ])
        for label in ("Purpose", "State"):
            self.assertIn(f"<dt>{label}</dt>", one)
        person = text[found[2][1]:found[2][2]]
        for label in ("Will provide", "Waiting for", "No person named"):
            self.assertIn(label, person)

    def test_escaping_rules_make_record_text_plain_text(self):
        rules = template_rules()
        self.assertEqual(rules, [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&#39;")])
        # The add-in gives the same rules in the same order.
        self.assertEqual(ADD_IN_RULE.findall(read(ADD_IN)), rules)
        block = first_item_block()
        expected_tags = [tag for tag, _ in Page(f"<html><ul>{block}</ul></html>").tags]
        for hostile in HOSTILE:
            with self.subTest(text=hostile):
                escaped = escape(hostile, rules)
                self.assertIsNone(re.search(r"[<>\"']", escaped))
                self.assertEqual(html.unescape(escaped), hostile)
                filled = Page("<html><ul>" + re.sub(r"\{\{[^}]*\}\}", lambda _: escaped, block) + "</ul></html>")
                self.assertEqual(filled.problems, [])
                self.assertEqual([tag for tag, _ in filled.tags], expected_tags)
                self.assertEqual(filled.comments, [])
                self.assertIn(" ".join(hostile.split()), filled.items[0])
        # The order matters: escaping & last would turn &lt; into &amp;lt; and change the text.
        wrong_order = rules[1:] + rules[:1]
        self.assertNotEqual(html.unescape(escape("<b>", wrong_order)), "<b>")

    def test_add_in_makes_a_dated_page_and_a_chat_summary(self):
        text = read(ADD_IN)
        self.assertIn("](overview-template.html)", text)
        gives_back = section(text, "What it gives back")
        for phrase in ("`Views/`", "self-contained HTML file", "snapshot, never an authority",
                       "short summary in chat", "read back", "as at", "searched", "could not be read"):
            self.assertIn(phrase, gives_back)
        steps = section(text, "Steps")
        self.assertIn("`Views/2026-10-23-project-overview.html`", steps)
        self.assertIn("Never replace an existing page", steps)
        self.assertIn("Only then call it saved", steps)
        self.assertIn("show both together and ask which stands", steps)
        self.assertIn("Keep the record's own words and states", steps)
        self.assertIn("../../Help/hosts-and-views.md", gives_back)

    def test_only_project_overview_makes_a_page(self):
        shipped = ROOT / "PACE/Product/Pace add-ins"
        for add_in in sorted(shipped.glob("*/ADD-IN.md")):
            if add_in.parent.name == "Project overview":
                continue
            with self.subTest(add_in=add_in.parent.name):
                text = read(add_in)
                self.assertNotIn(".html", text)
                self.assertNotIn("template", text)
                self.assertEqual(sorted(p.name for p in add_in.parent.iterdir()), ["ADD-IN.md", "Launchers"])
        self.assertIn("None switched on yet.", read(ROOT / "PACE/Pace.md"))


class ExamplePageTests(unittest.TestCase):
    def setUp(self):
        self.text = read(EXAMPLE_PAGE)
        self.page = Page(self.text)

    def test_example_page_is_well_formed_html_with_nothing_external(self):
        self.assertTrue(self.text.startswith("<!DOCTYPE html>\n<html lang=\"en-NZ\">\n<head>\n<meta charset=\"utf-8\">\n"))
        self.assertEqual(self.page.problems, [])
        self.assertEqual(self.page.doctype, "DOCTYPE html")
        self.assertIsNone(FORBIDDEN.search(self.text))
        tags = [tag for tag, _ in self.page.tags]
        for tag in ("html", "head", "title", "style", "body", "main", "header", "footer"):
            self.assertEqual(tags.count(tag), 1, tag)
        self.assertNotIn("{{", self.text)
        self.assertNotIn("}}", self.text)
        body = without_comments_and_style(self.text)
        self.assertIsNone(BAD_AMPERSAND.search(body))
        for name in re.findall(r"&([A-Za-z][A-Za-z0-9]*);", body):
            self.assertIn(name + ";", NAMED_ENTITIES)

    def test_example_page_is_the_template_filled_in(self):
        template = read(TEMPLATE)
        self.assertEqual(self.page.style, Page(template).style)
        self.assertEqual(self.page.comments, ["start: every project view", "end: every project view"])
        # Every class used is one the template uses or its fill-in note names, so the page adds no styling.
        note = re.match(r"<!DOCTYPE html>\n<!--(.*?)-->", template, re.S).group(1)
        named = {name for value in re.findall(r'class="([^"]+)"', note) for name in value.split()}
        self.assertLessEqual(self.page.classes(), Page(template).classes() | named)
        footer = re.search(r'<footer class="foot">.*?</footer>', template, re.S).group(0)
        self.assertIn(footer, self.text)
        header = self.text[self.text.index("<header>"):self.text.index("</header>")]
        self.assertIn(f'<p class="product">{PRODUCT_NAME}</p>', header)
        facts = re.findall(r"<dt>(.*?)</dt>\n<dd>(.*?)</dd>", header)
        self.assertEqual([name for name, _ in facts], list(FACTS))
        for name, value in facts:
            self.assertTrue(value.strip(), name)
        made = date.fromisoformat(EXAMPLE_PAGE.name[:10])
        self.assertIn(long_date(made), dict(facts)["As at"])
        self.assertIn("Record/", dict(facts)["Searched"])
        self.assertRegex(self.text, rf"<title>Project overview, {short_date(made)} - {PRODUCT_NAME}</title>")

    def test_example_page_keeps_each_records_own_words(self):
        self.assertGreater(len(self.page.items), 3)
        for item in self.page.items:
            with self.subTest(item=item[:40]):
                ids = re.findall(r"\bRecord (\S+)$", item)
                self.assertEqual(len(ids), 1)
                path = EXAMPLE / "Record" / f"{ids[0]}.md"
                self.assertTrue(path.is_file(), path)
                fields, body, problems = pr.parse(path.read_bytes())
                self.assertEqual(problems, [])
                self.assertIn(" ".join(body.split()), item)
                state = (fields.get("state") or [""])[0]
                if state:
                    self.assertRegex(item, rf"\b{state}\b")
                due = (fields.get("due") or [""])[0]
                if due:
                    self.assertIn(f"due {short_date(date.fromisoformat(due))}", item)

    def test_example_page_shows_both_accounts_side_by_side(self):
        start = self.text.index('<div class="line two-ways">')
        both = self.text[start:self.text.index("</div>", start)]
        for request in ("20261027T020000Z--maple-budget--brd002", "20261027T220000Z--maple-budget--brd003"):
            self.assertIn(f"Record {request}", both)
            fields, _, _ = pr.parse((EXAMPLE / "Record" / f"{request}.md").read_bytes())
            self.assertEqual(fields["corrects"], ["20261025T210000Z--maple-budget--brd001"])
        self.assertIn("which stands?", both)

    def test_example_page_escapes_record_text(self):
        record = read(EXAMPLE / "Record/20261025T204000Z--maple-budget--csl001.md")
        self.assertIn("<Drivers & Inputs>", record)
        self.assertIn("&lt;Drivers &amp; Inputs&gt;", self.text)
        self.assertNotIn("<Drivers", self.text)
        self.assertIn("<Drivers & Inputs>", "".join(self.page.text))
        self.assertNotIn("drivers", {tag for tag, _ in self.page.tags})

    def test_example_carries_the_same_add_in_files(self):
        for name in ("ADD-IN.md", "overview-template.html"):
            with self.subTest(file=name):
                self.assertEqual((EXAMPLE / ADD_IN_FOLDER / name).read_bytes(), (ROOT / "PACE" / ADD_IN_FOLDER / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
