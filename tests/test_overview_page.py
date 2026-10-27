"""Project overview page checks, against the shipped template and the invented example only.

The template beside the Project overview add-in is the one source of the page:
the overview tool takes its style, wordmark and footer from it, and an assistant
without Python fills it in by hand. These checks read the template, the add-in,
and the invented example page the tool made from the example folder. They
never open an owner's folder.
"""

from datetime import date
from html.entities import html5 as NAMED_ENTITIES
from html.parser import HTMLParser
from pathlib import Path
import html
import importlib.util
import re
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
ADD_IN_FOLDER = Path("Product/Pace add-ins/Project overview")
TEMPLATE = ROOT / "PACE" / ADD_IN_FOLDER / "overview-template.html"
ADD_IN = ROOT / "PACE" / ADD_IN_FOLDER / "ADD-IN.md"
TOOL = ROOT / "PACE/Product/Tools/pace_overview.py"
HOSTS_HELP = ROOT / "PACE/Product/Help/hosts-and-views.md"
EXAMPLE = ROOT / "example"
EXAMPLE_PAGE = EXAMPLE / "2 Views/2026-10-30-project-overview.html"
EXAMPLE_AS_AT = "2026-10-30T09:00:00+13:00"

_spec = importlib.util.spec_from_file_location("pace_record", ROOT / "PACE/Product/Tools/pace_record.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)
_spec = importlib.util.spec_from_file_location("pace_overview", TOOL)
po = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(po)

PRODUCT_NAME = "Pace by SBR"
VIEWS = ("every project", "one project", "by person")
ABOUT = ("Asked", "Searched", "Could not read")
# SBR brand kit edition 02: plum, citron, warm paper, stone and olive, with tints of them for panels and quiet text.
BRAND = {"#35293d", "#dbf36b", "#faf6f0", "#e9e0d8", "#4f5c10"}
TINTS = {"#f2ebe2", "#5e5068", "#3f3248", "#c9bad6", "#5a4a66", "#ffffff", "#4b3f55", "#b5a79a"}

# Everything a page may contain. No element or attribute here can run code or fetch anything.
COMMON_ATTRIBUTES = {"lang", "charset", "name", "content", "class"}
TAG_ATTRIBUTES = {
    "details": {"class", "open", "id"},
    "li": {"class", "data-no", "data-request", "data-requests"},  # a numbered line's number and request id, never shown
    "a": {"class", "href"},
    "ol": {"class", "type"},  # an item recorded two ways letters its accounts, so they never look like its number
    "svg": {"class", "viewbox", "role", "aria-label"},
    "path": {"d", "transform", "fill"},
    "rect": {"x", "y", "width", "height", "fill"},
}
ALLOWED_TAGS = {
    "html", "head", "meta", "title", "style", "body", "main", "header", "footer", "section",
    "article", "div", "h1", "h2", "h3", "p", "dl", "dt", "dd", "ul", "ol", "li", "strong", "span",
    "details", "summary", "svg", "path", "rect", "a",
}
VOID = {"meta"}
SVG_CHILDREN = {"path", "rect"}
PHRASING = {"strong", "span", "a"}
HEAD_CHILDREN = {"meta", "title", "style"}
FORBIDDEN = re.compile(
    r"<\s*(?:script|link|img|iframe|frame|object|embed|base|form|input|button|math|video|audio|source|picture|image|use|foreignobject)\b"
    r"|<\s*a\b(?! class=\"jump\" href=\"#p-(?:[a-z0-9-]+|\{\{project id\}\}(?:--own)?)\">)"
    r"|\b(?:src|xlink:href|srcset|action|style)\s*="
    r"|\bhref\s*=(?!\"#p-(?:[a-z0-9-]+|\{\{project id\}\}(?:--own)?)\">)"
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
    "<svg onload=alert(1)><path d=\"M0\"/></svg>",
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
        self.ids = []
        self.jumps = []
        self._stack = []
        self._open_items = []
        self._details_children = []
        self.feed(text)
        self.close()
        if self._stack:
            self.problems.append(f"not closed: {[tag for tag, _ in self._stack]}")
        made = [ident for ident in self.ids if "{{" not in ident]  # a template's placeholders repeat by design
        if len(set(made)) != len(made):
            self.problems.append("an id is used twice")
        missing = sorted(set(jump[1:] for jump in self.jumps if "{{" not in jump) - set(made))
        if missing:
            self.problems.append(f"a jump to no row: {missing}")

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
        if parent in ("p", "h1", "h2", "h3", "dt", "strong", "span", "summary") and tag not in PHRASING:
            self.problems.append(f"{tag} inside {parent}")
        if parent in ("ul", "ol") and tag != "li":
            self.problems.append(f"{tag} directly inside {parent}")
        if parent == "dl" and tag not in ("dt", "dd"):
            self.problems.append(f"{tag} directly inside dl")
        if tag == "li" and parent not in ("ul", "ol"):
            self.problems.append(f"li inside {parent}")
        if tag in ("dt", "dd") and parent != "dl":
            self.problems.append(f"{tag} inside {parent}")
        if (tag in SVG_CHILDREN) != (parent == "svg"):
            self.problems.append(f"{tag} inside {parent}")
        if tag == "svg" and parent != "div":
            self.problems.append(f"svg inside {parent}")
        if parent == "details":
            if not self._details_children[-1] and tag != "summary":
                self.problems.append("details does not start with summary")
            self._details_children[-1].append(tag)
        if tag == "summary" and parent != "details":
            self.problems.append(f"summary inside {parent}")
        if tag == "a" and any(open_tag == "summary" for open_tag, _ in self._stack):
            self.problems.append("a link inside a line's summary, which is already a control")

    def _record_tag(self, tag, attrs):
        values = dict(attrs)
        if len(values) != len(attrs):
            self.problems.append(f"repeated attribute on {tag}")
        allowed = TAG_ATTRIBUTES.get(tag, COMMON_ATTRIBUTES)
        for name, value in values.items():
            if name not in allowed:
                self.problems.append(f"attribute not allowed: {tag} {name}")
            if name == "fill" and value != "currentColor":
                self.problems.append(f"fill other than currentColor: {value}")
            if name == "href":
                if not re.fullmatch(r"#p-[a-z0-9-]+|#p-\{\{project id\}\}(?:--own)?", value or ""):
                    self.problems.append(f"a link that is not a jump within the page: {value}")
                self.jumps.append(value)
            if name == "id":
                self.ids.append(value)
            if name == "data-no" and not re.fullmatch(r"[1-9]\d*|\{\{its number\}\}", value or ""):
                self.problems.append(f"a number that is not a number: {value}")
            if name in ("data-request", "data-requests") and not re.fullmatch(
                    r"\d{8}T\d{6}Z--[a-z0-9-]+--[a-z0-9]{6}( \d{8}T\d{6}Z--[a-z0-9-]+--[a-z0-9]{6})*|\{\{[^}]+\}\}", value or ""):
                self.problems.append(f"{name} that is not request ids: {value}")
        self.tags.append((tag, values))
        return values

    def handle_starttag(self, tag, attrs):
        self._check_place(tag)
        values = self._record_tag(tag, attrs)
        for _, parts in self._open_items:
            parts.append(" ")  # a new element starts a new word, as it reads on the page
        if tag in VOID:
            return
        self._stack.append((tag, values.get("class", "").split()))
        if tag == "details":
            self._details_children.append([])
        if tag == "li" and "item" in self._stack[-1][1]:
            self._open_items.append((len(self._stack), []))

    def handle_startendtag(self, tag, attrs):
        self._check_place(tag)
        self._record_tag(tag, attrs)
        if tag not in VOID and tag not in SVG_CHILDREN:
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
        if tag == "details":
            self._details_children.pop()
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
    return re.search(r'<li class="item[^"]*">.*?</li>', read(TEMPLATE), re.S).group(0)


def views(text):
    found = []
    for view in VIEWS:
        start = text.find(f"<!-- start: {view} view -->")
        end = text.find(f"<!-- end: {view} view -->")
        if start != -1 or end != -1:
            found.append((view, start, end))
    return found


def wordmark(text):
    return re.search(r'<svg class="wordmark".*?</svg>', text, re.S).group(0)


def long_date(day):
    return f"{day.day} {day:%B %Y}"


def short_date(day):
    return f"{day.day} {day:%b %Y}"


def luminance(colour):
    channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(one, two):
    high, low = sorted((luminance(one), luminance(two)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def palettes(style):
    light = dict(re.findall(r"(--[a-z-]+): (#[0-9a-f]{6});", re.search(r":root \{(.*?)\}", style, re.S).group(1)))
    found = {"light": light}
    for name, media in (("dark", "@media (prefers-color-scheme: dark)"), ("print", "@media print")):
        block = re.search(rf"{re.escape(media)} \{{\s*:root \{{(.*?)\}}", style, re.S).group(1)
        found[name] = dict(re.findall(r"(--[a-z-]+): (#[0-9a-f]{6});", block))
    return found


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
        found = palettes(style)
        self.assertGreater(len(found["light"]), 5)
        self.assertEqual(set(found["dark"]), set(found["light"]))
        self.assertEqual(set(found["print"]), set(found["light"]))
        for line in style.splitlines():
            if re.search(r"#[0-9a-fA-F]{3,6}\b", line):
                self.assertRegex(line, r"^\s*--[a-z-]+: #[0-9a-f]{6};$")

    def test_template_uses_the_sbr_brand(self):
        style = Page(read(TEMPLATE)).style
        found = palettes(style)
        colours = set().union(*(set(palette.values()) for palette in found.values()))
        self.assertLessEqual(colours, BRAND | TINTS)  # never red and green: the brand's own colours and tints of them
        light, dark = found["light"], found["dark"]
        self.assertEqual((light["--bg"], light["--text"], light["--rule"], light["--accent"], light["--mark"]),
                         ("#faf6f0", "#35293d", "#e9e0d8", "#4f5c10", "#dbf36b"))  # paper, plum, stone, olive, citron
        self.assertEqual((dark["--bg"], dark["--text"], dark["--accent"]), ("#35293d", "#faf6f0", "#dbf36b"))
        # Text holds at least 4.5:1 against both its backgrounds in every scheme, and citron is only a fill behind plum.
        for scheme, palette in found.items():
            for ink in ("--text", "--muted", "--accent"):
                for ground in ("--bg", "--panel"):
                    with self.subTest(scheme=scheme, ink=ink, ground=ground):
                        self.assertGreaterEqual(contrast(palette[ink], palette[ground]), 4.5)
            self.assertGreaterEqual(contrast(palette["--on-mark"], palette["--mark"]), 4.5)
        self.assertIn('font: 15px/1.5 "Instrument Sans", Arial, sans-serif;', style)
        self.assertIn("h1, h2, h3 { font-weight: 500; letter-spacing: -0.02em; }", style)
        # The SBR wordmark is the brand kit's artwork, drawn in the text colour so it reverses in dark mode.
        mark = wordmark(read(TEMPLATE))
        self.assertTrue(mark.startswith('<svg class="wordmark" viewBox="0 0 714.2091 399.0466" role="img" aria-label="SBR">'))
        self.assertEqual((mark.count("<path "), mark.count("<rect ")), (3, 2))
        self.assertEqual(mark.count('fill="currentColor"'), 5)
        self.assertIn(".wordmark { display: block; width: 7rem; height: auto; color: var(--text); }", style)  # 88 px or more of visible mark

    def test_template_has_the_three_views_and_the_lines_every_page_needs(self):
        text = read(TEMPLATE)
        found = views(text)
        self.assertEqual([view for view, _, _ in found], list(VIEWS))
        header_end = text.index("</header>")
        about_start = text.index('<section class="about">')
        footer_start = text.index('<footer class="foot">')
        for view, start, end in found:
            with self.subTest(view=view):
                self.assertTrue(header_end < start < end < about_start < footer_start)
                self.assertEqual(text.count(f"<!-- start: {view} view -->"), 1)
        # The as-at moment heads every page; what was asked and searched, and anything not read, close it.
        header = text[text.index("<header>"):header_end]
        self.assertIn('<p class="asat">As at {{', header)
        self.assertIn('<p class="partial">Partial: ', header)
        self.assertEqual(re.findall(r"<dt>(.*?)</dt>", text[about_start:footer_start]), list(ABOUT) + ["Housekeeping"])
        self.assertIn(f'<p class="product">{PRODUCT_NAME}</p>', header)
        self.assertIn(wordmark(text), header)
        self.assertIn(f"<p>{PRODUCT_NAME}</p>", text[footer_start:])
        self.assertRegex(text, rf"<title>[^<]+ - {PRODUCT_NAME}</title>")
        every, one, person = (text[start:end] for _, start, end in found)
        for view in (every, one, person):
            self.assertEqual(re.findall(r'<p class="stat[^"]*"><strong>\{\{number\}\}</strong> ([^<]+)</p>', view),
                             ["overdue", "due today", "due in the next 7 days"])
            self.assertIn('<details class="week">', view)
            self.assertIn('<section class="part two-ways">', view)
        self.assertEqual(re.findall(r"<h2>(\w[^<]*?) <span", every), ["Recorded two ways", "Needs attention", "Projects"])
        self.assertEqual(re.findall(r"<h2>(\w[^<]*?) <span", one), ["Recorded two ways", "Needs attention", "Projects",
                                                                   "Needs attention", "Open work", "Last three weeks"])
        self.assertEqual(re.findall(r"<h2>(\w[^<]*?) <span", person), ["Recorded two ways", "Needs attention", "People"])
        # Projects are rows that open: a project with projects inside it, its own work, and every other project.
        for kind in ('<details class="node parent" id="p-{{project id}}" open>', '<details class="node own" id="p-{{project id}}--own">',
                     '<details class="node" id="p-{{project id}}">'):
            self.assertIn(kind, every)
        self.assertIn('<a class="jump" href="#p-{{project id}}">', every)
        self.assertIn('<details class="files">', one)
        for label in ("You owe or Owes", "Waiting for", "No person named", '<details class="fold">', '<details class="node person" open>'):
            self.assertIn(label, person)
        style = Page(text).style
        narrow = style[style.index("@media (max-width: 40rem)"):style.index("@media print")]
        self.assertIn(".heads { display: none; }", narrow)
        self.assertIn(".node > summary .num, .node > summary .last { display: none; }", narrow)
        printed = style[style.index("@media print"):]
        # Printing opens every project and person, so every item prints as its one line; the lines stay closed.
        self.assertIn(".node::details-content, .fold::details-content, .files::details-content { content-visibility: visible; display: block; }", printed)

    def test_every_line_can_be_read_and_reached_by_anyone(self):
        style = Page(read(TEMPLATE)).style
        # Fading text with opacity would take muted text below 4.5:1, so quiet text uses the muted colour alone.
        self.assertNotIn("opacity", style)
        self.assertIn(":focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }", style)
        self.assertIn("summary { cursor: pointer; }", style)
        self.assertIn(".stat.zero strong { color: var(--muted); font-weight: 400; }", style)
        # A long project name never squeezes the subject, a tag wraps on a phone, and long words break.
        self.assertIn(".side { max-width: 18rem;", style)
        narrow = style[style.index("@media (max-width: 40rem)"):style.index("@media print")]
        self.assertIn(".tag { white-space: normal; }", narrow)
        self.assertIn("h1, .lead, .known, .sub, .meta, .group, .quiet, .none, .fold > summary, .week > summary { overflow-wrap: anywhere; }", style)
        # The row of a project's own work gives no facts: the row above it does.
        self.assertNotIn('<span class="itself">itself</span></span> <span class="status">', read(TEMPLATE))

    def test_escaping_rules_make_record_text_plain_text(self):
        rules = template_rules()
        self.assertEqual(rules, [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&#39;")])
        # The add-in and the tool use the same rules in the same order.
        self.assertEqual(ADD_IN_RULE.findall(read(ADD_IN)), rules)
        self.assertEqual(list(po.ESCAPES), rules)
        block = first_item_block()
        expected_tags = [tag for tag, _ in Page(f"<html><ul>{block}</ul></html>").tags]
        for hostile in HOSTILE:
            with self.subTest(text=hostile):
                escaped = escape(hostile, rules)
                self.assertEqual(po.esc(hostile), escaped)
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
        for phrase in ("`2 Views/`", "self-contained HTML file", "SBR's brand", "snapshot, never an authority",
                       "short summary in chat", "read back", "as at", "searched", "could not be read"):
            self.assertIn(phrase, gives_back)
        steps = section(text, "Steps")
        for phrase in ("`2 Views/2026-10-23-project-overview.html`", "Never replace an existing page", "Only then call it saved",
                       "show both together and ask which stands", "Keep the record's own words and states",
                       "Do not add a priority, percent complete, on-track or health judgement", "never call related work blocking",
                       "Needs attention", "Waiting on you", "waiting on others", "no person named", "the longest late first"):
            self.assertIn(phrase, steps)
        self.assertIn("../../Help/hosts-and-views.md", gives_back)

    def test_help_gives_the_tool_route_and_the_add_in_points_to_it(self):
        # Add-ins stay in plain words; the tool's commands live in the views help, as the record tool's live in records help.
        tool_help = section(read(HOSTS_HELP), "The overview tool")
        commands = re.findall(r"^python3 Product/Tools/pace_overview\.py (.*)$", tool_help, re.M)
        self.assertEqual(len(commands), 4)
        parser = po.build_parser()
        for command in commands:
            with self.subTest(command=command):
                args = parser.parse_args(re.sub(r'"<[^>]*>"|<[^>]*>', "x", command).split())
                self.assertEqual(args.save, not args.review)  # the review list is for chat and never saved
                self.assertIsNone(args.owner)  # the owner's names come from Pace.md's Owner: lines
        self.assertIn("--project", commands[1])
        self.assertIn("--by-person", commands[2])
        self.assertEqual(commands[3], "--review")
        self.assertIn("The owner's names come from the `Owner:` lines in `Pace.md`", tool_help)
        for phrase in ("Python 3.9 or later", "never replacing a file", "reads it back", "--template",
                       "takes only the style block, wordmark and footer from it",
                       "`saved` only when the page was saved and read back", "`placed-not-confirmed`", "`not-made`",
                       "no `Pace project.md`", "It changes no record."):
            self.assertIn(phrase, tool_help)
        for status in ("saved", "placed-not-confirmed", "not-saved", "not-made"):
            self.assertIn(f'"{status}"', read(TOOL))
        steps = section(read(ADD_IN), "Steps")
        self.assertIn('following "The overview tool" in [Assistants and dated views](../../Help/hosts-and-views.md)', steps)
        self.assertIn("takes only the style, wordmark and footer from the template it is given", steps)
        self.assertIn("fill in the copy's template by hand instead", steps)
        self.assertIn("`saved` means saved and read back", steps)
        self.assertIn("**Otherwise, fill in the template by hand**", steps)
        self.assertIn("if anything could not be read, the page says it is partial", steps)
        self.assertNotIn("python3", read(ADD_IN))

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
        for tag in ("html", "head", "title", "style", "body", "main", "header", "footer", "svg"):
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
        self.assertEqual(wordmark(self.text), wordmark(template))
        self.assertEqual(self.page.comments, ["start: every project view", "end: every project view"])
        # Every class used is one the template uses or its fill-in note names, so the page adds no styling.
        note = re.match(r"<!DOCTYPE html>\n<!--(.*?)-->", template, re.S).group(1)
        named = {name for value in re.findall(r'class="([^"]+)"', note) for name in value.split()}
        self.assertLessEqual(self.page.classes(), Page(template).classes() | named)
        footer = re.search(r'<footer class="foot">.*?</footer>', template, re.S).group(0)
        self.assertIn(footer, self.text)
        header = self.text[self.text.index("<header>"):self.text.index("</header>")]
        self.assertIn(f'<p class="product">{PRODUCT_NAME}</p>', header)
        about = self.text[self.text.index('<section class="about">'):self.text.index('<footer class="foot">')]
        facts = re.findall(r"<dt>(.*?)</dt>\n<dd>(.*?)</dd>", about)
        self.assertEqual([name for name, _ in facts], list(ABOUT))
        for name, value in facts:
            self.assertTrue(value.strip(), name)
        made = date.fromisoformat(EXAMPLE_PAGE.name[:10])
        self.assertIn(f'<p class="asat">As at Friday {long_date(made)}, 9:00 am NZDT</p>', header)
        self.assertIn("Record/", dict(facts)["Searched"])
        self.assertRegex(self.text, rf"<title>Project overview, {short_date(made)} - {PRODUCT_NAME}</title>")

    def test_example_page_is_exactly_what_the_tool_makes_from_the_example(self):
        with tempfile.TemporaryDirectory(prefix="pace-overview-example-") as temporary:
            copy = Path(temporary) / "example"
            shutil.copytree(EXAMPLE, copy, ignore=shutil.ignore_patterns("__pycache__"))
            (copy / "2 Views" / EXAMPLE_PAGE.name).unlink()
            args = po.build_parser().parse_args(["--pace", str(copy), "--as-at", EXAMPLE_AS_AT, "--save"])
            out, code = po.run(args)
            self.assertEqual((out["status"], code, out["page"]), ("saved", 0, f"2 Views/{EXAMPLE_PAGE.name}"), out)
            self.assertEqual((copy / out["page"]).read_bytes(), EXAMPLE_PAGE.read_bytes())

    def test_example_page_keeps_each_records_own_words(self):
        records = []
        for path in sorted((EXAMPLE / "Record").glob("*.md")):
            fields, body, problems = pr.parse(path.read_bytes())
            if fields is not None and not problems:
                records.append((fields, " ".join(body.split())))
        self.assertGreater(len(self.page.items), 5)
        for item in self.page.items:
            with self.subTest(item=item[:40]):
                # Each item is one record, word for word, found by its own text (and its subject when texts repeat).
                found = [(fields, body) for fields, body in records if body and body in item]
                if len(found) > 1:
                    found = [(fields, body) for fields, body in found if (fields.get("subject") or [""])[0] in item]
                self.assertEqual(len(found), 1, item)
                fields = found[0][0]
                state = (fields.get("state") or [""])[0]
                if state:
                    self.assertRegex(item, rf"\b{state}\b")
                due = (fields.get("due") or [""])[0]
                if due:
                    self.assertIn(f"due {short_date(date.fromisoformat(due))}", item)

    def test_example_page_shows_both_accounts_side_by_side_and_counts_them_nowhere_else(self):
        start = self.text.index('<section class="part two-ways">')
        both = self.text[start:self.text.index("</section>", start)]
        for request in ("20261027T020000Z--maple-budget--brd002", "20261027T220000Z--maple-budget--brd003"):
            fields, body, _ = pr.parse((EXAMPLE / "Record" / f"{request}.md").read_bytes())
            self.assertEqual(fields["corrects"], ["20261025T210000Z--maple-budget--brd001"])
            words = po.esc(" ".join(body.split()))
            self.assertIn(words, both)
            self.assertEqual(self.text.count(words), 1)
        self.assertIn("Ask the owner which stands.", both)
        _, first, _ = pr.parse((EXAMPLE / "Record/20261025T210000Z--maple-budget--brd001.md").read_bytes())
        self.assertNotIn(po.esc(" ".join(first.split())), self.text)

    def test_pages_show_no_record_references(self):
        # A numbered line keeps its request id in data-request, so a later chat can find it by its number; it is
        # never shown on the page.
        shown = re.sub(r' data-requests?="[^"]*"', "", self.text)
        self.assertNotRegex(shown, r"\d{8}T\d{6}Z--")
        self.assertNotIn('class="ref"', self.text)
        self.assertNotIn("{{the request id", re.sub(r' data-requests?="[^"]*"', "", read(TEMPLATE)))

    def test_example_page_puts_what_is_late_first(self):
        start = self.text.index("<h2>Needs attention")
        attention = self.text[start:self.text.index("</section>", start)]
        late = attention.index(po.esc("Sam to send the cost centre list for the <Drivers & Inputs> tab."))
        self.assertLess(late, attention.index(po.esc("Owner to sign off the wage assumptions so Ana can finish the staff costs.")))
        # A mixed list names each item's project; opening the line gives a jump to the project's row.
        self.assertIn('<span class="side">Maple Lantern &rsaquo; Budget 2027</span>', attention)
        self.assertIn('<p class="go"><a class="jump" href="#p-maple-budget">Go to Maple Lantern &rsaquo; Budget 2027</a></p>', attention)
        self.assertIn('<span class="tag late">2 days late</span>', attention)
        self.assertIn('<p class="stat hot"><strong>1</strong> overdue</p>', self.text)
        self.assertIn('<details class="node" id="p-maple-budget">', self.text)

    def test_example_page_shows_the_last_7_days_and_each_project_as_a_row(self):
        self.assertIn('<summary>Last 7 days: <strong>3</strong> new &middot; <strong>1</strong> done</summary>', self.text)
        projects = self.text[self.text.index("<h2>Projects"):]
        self.assertIn('<details class="node parent" id="p-maple-lantern" open>', projects)
        self.assertIn('<span class="pname">Budget 2027</span> <span class="status">', projects)

    def test_example_page_escapes_record_text(self):
        record = read(EXAMPLE / "Record/20261025T204000Z--maple-budget--csl001.md")
        self.assertIn("<Drivers & Inputs>", record)
        self.assertIn("&lt;Drivers &amp; Inputs&gt;", self.text)
        self.assertNotIn("<Drivers", self.text)
        self.assertIn("<Drivers & Inputs>", "".join(self.page.text))
        self.assertNotIn("drivers", {tag for tag, _ in self.page.tags})

    def test_example_carries_the_same_add_in_files_and_tool(self):
        for name in ("ADD-IN.md", "overview-template.html"):
            with self.subTest(file=name):
                self.assertEqual((EXAMPLE / ADD_IN_FOLDER / name).read_bytes(), (ROOT / "PACE" / ADD_IN_FOLDER / name).read_bytes())
        self.assertEqual((EXAMPLE / "Product/Tools/pace_overview.py").read_bytes(), TOOL.read_bytes())


if __name__ == "__main__":
    unittest.main()
