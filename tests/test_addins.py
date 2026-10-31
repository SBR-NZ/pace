"""Add-in checks against the invented PACE folder only.

`Chat` below is a small model of the routing written in PACE/Pace.md and
PACE/Product/Help/add-ins.md. It plays invented chats against a copy of the
real PACE folder files: what is opened at the start of a chat, which file a
request opens, and which copy of an add-in wins.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACE_FOLDER = ROOT / "PACE"
YOUR_LINES = "<!-- Your lines go below this one. Pace updates never change them. -->"
SHIPPED = Path("Product/Pace add-ins")
MY_ADD_INS = Path("3 My add-ins")
OLDER_MY_ADD_INS = Path("Pace/Add-ins/My add-ins")  # where an older folder keeps them
HELP = PACE_FOLDER / "Product/Help/add-ins.md"

CATALOGUE = (
    "Getting started",
    "Daily brief",
    "Project overview",
    "Key numbers and changes",
    "What was reported",
    "Reminders",
    "Open work",
    "Weekly review",
    "Power BI",
    "Xero",
    "Contracts",
)
HEADINGS = ("When to use it", "What it needs", "Steps", "What it gives back", "Limits")
INDEX_LINE = re.compile(r"^- \*\*(?P<name>[^*]+)\*\* - (?P<purpose>[^`]+?) `(?P<path>[^`]+/ADD-IN\.md)`$")
PURPOSE = re.compile(r"^\*\*Purpose:\*\* (?P<purpose>.+)$", re.M)
LINK = re.compile(r"\]\(([^)\s]+)\)")
OLD_TOOLING = re.compile(
    r"pace-|--[a-z]|Product/tools|`Working/|\.json|checked save|agree-query|generation|\b(?:request|person|task|project):[<0-9a-f]",
    re.I,
)
SIGNING = re.compile(r"\bsignatures?\b|\bsigning\b|\bsigned approvals?\b|approval key|publisher", re.I)


def section(text, heading):
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if match is None:
        raise AssertionError(f"missing section: {heading}")
    return match.group(1)


@dataclass(frozen=True)
class Entry:
    name: str
    purpose: str
    path: str


def index_entries(pace_text):
    entries = []
    for line in section(pace_text, "Add-in index").splitlines():
        if line.startswith("- "):
            match = INDEX_LINE.match(line)
            if match is None:
                raise ValueError(f"index line not in the documented form: {line}")
            entries.append(Entry(match["name"], match["purpose"], match["path"]))
    return entries


def catalogue_lines():
    block = re.search(r"```text\n(.*?)```", section(HELP.read_text(encoding="utf-8"), "Switching one on or off"), re.S)
    return [line for line in block.group(1).splitlines() if line]


@dataclass(frozen=True)
class Outcome:
    action: str  # "none", "open", "ask", "off" or "missing"
    names: tuple = ()


class Chat:
    """One invented chat in a copied Pace folder."""

    def __init__(self, folder):
        self.folder = folder
        # Only Pace.md is read when a chat starts.
        self.opened = [folder / "Pace.md"]
        self.index = index_entries((folder / "Pace.md").read_text(encoding="utf-8"))

    def ask(self, request):
        wanted = request.lower()
        fits = [entry for entry in self.index if entry.name.lower() in wanted]
        if not fits:
            shipped = sorted(p.name for p in (self.folder / SHIPPED).iterdir() if p.name.lower() in wanted)
            return Outcome("off", tuple(shipped)) if shipped else Outcome("none")
        if len(fits) > 1:
            return Outcome("ask", tuple(entry.name for entry in fits))
        path = self.folder / fits[0].path
        if not path.is_file():
            return Outcome("missing", (fits[0].path,))
        self.opened.append(path)
        return Outcome("open", (fits[0].name,))


class InventedFolder:
    """A throwaway copy of PACE that an invented owner changes."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "Pace"
        shutil.copytree(PACE_FOLDER, self.root)
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()

    def switch_on(self, *names):
        lines = {INDEX_LINE.match(line)["name"]: line for line in catalogue_lines()}
        self.set_index([lines[name] for name in names])

    def set_index(self, lines):
        pace = self.root / "Pace.md"
        text = pace.read_text(encoding="utf-8")
        body = section(text, "Add-in index")
        intro = body.split("\n\n")[0]
        # Index lines go below the "Your lines" mark, as the add-ins help says, so updates never change them.
        pace.write_text(text.replace(body, intro + "\n\n" + YOUR_LINES + "\n" + "\n".join(lines) + "\n\n"), encoding="utf-8")

    def customise(self, name, copy_name):
        copy = self.root / MY_ADD_INS / copy_name
        shutil.copytree(self.root / SHIPPED / name, copy)
        add_in = copy / "ADD-IN.md"
        title, rest = add_in.read_text(encoding="utf-8").split("\n", 1)
        add_in.write_text(
            f"{title}\n\n**Customised from:** {name}\n{rest}\n- Invented owner change: list client calls first.\n",
            encoding="utf-8",
        )
        return add_in


def shipped_add_in(name):
    return PACE_FOLDER / SHIPPED / name / "ADD-IN.md"


class ShippedAddInTests(unittest.TestCase):
    def test_catalogue_is_the_classified_workflows(self):
        folders = {p.name for p in (PACE_FOLDER / SHIPPED).iterdir()}
        self.assertEqual(folders, set(CATALOGUE))

    def test_each_add_in_follows_the_format(self):
        for name in CATALOGUE:
            with self.subTest(add_in=name):
                text = shipped_add_in(name).read_text(encoding="utf-8")
                self.assertTrue(text.startswith(f"# {name}\n\n**Purpose:** "))
                self.assertEqual(len(PURPOSE.findall(text)), 1)
                headings = re.findall(r"^## (.+)$", text, re.M)
                self.assertEqual(tuple(headings), HEADINGS)
                self.assertRegex(section(text, "Steps"), r"(?m)^1\. ")
                self.assertIn("These steps apply only while", section(text, "Limits"))

    def test_help_lines_switch_on_each_shipped_add_in(self):
        lines = catalogue_lines()
        self.assertEqual(len(lines), len(CATALOGUE))
        for line in lines:
            match = INDEX_LINE.match(line)
            self.assertIsNotNone(match, line)
            with self.subTest(add_in=match["name"]):
                self.assertEqual(match["path"], f"{SHIPPED.as_posix()}/{match['name']}/ADD-IN.md")
                text = (PACE_FOLDER / match["path"]).read_text(encoding="utf-8")
                self.assertEqual(PURPOSE.search(text)["purpose"], match["purpose"])
        help_table = section(HELP.read_text(encoding="utf-8"), "Shipped add-ins")
        for name in CATALOGUE:
            self.assertIn(f"| {name} |", help_table)

    def test_no_old_record_commands_or_signing(self):
        files = [shipped_add_in(name) for name in CATALOGUE] + [HELP, PACE_FOLDER / "Pace.md"]
        for path in files:
            with self.subTest(path=path.relative_to(PACE_FOLDER)):
                text = path.read_text(encoding="utf-8")
                if path != HELP:  # help names the launchers' pace-... folders
                    self.assertIsNone(OLD_TOOLING.search(text))
                self.assertIsNone(SIGNING.search(text))
                self.assertNotIn("\u2014", text)

    def test_saving_points_to_record_help_and_links_resolve(self):
        for name in CATALOGUE:
            with self.subTest(add_in=name):
                path = shipped_add_in(name)
                text = path.read_text(encoding="utf-8")
                links = LINK.findall(text)
                self.assertIn("../../Help/records.md", links)
                for link in links:
                    self.assertTrue((path.parent / link).resolve().is_file(), link)
                if re.search(r"\bsaved?\b", text):
                    self.assertRegex(text, r"read-back|read back")
        for link in LINK.findall(HELP.read_text(encoding="utf-8")):
            self.assertTrue((HELP.parent / link).is_file(), link)

    def test_link_titles_match_the_title_of_the_page_they_open(self):
        for name in CATALOGUE:
            with self.subTest(add_in=name):
                path = shipped_add_in(name)
                for title, link in re.findall(r"\[([^\]]+)\]\(([^)\s]+\.md)\)", path.read_text(encoding="utf-8")):
                    target = (path.parent / link).resolve()
                    heading = target.read_text(encoding="utf-8").splitlines()[0]
                    self.assertEqual(heading, f"# {title}", f"{link} is titled {heading!r}")

    def test_switching_on_says_what_to_do_on_a_host_that_cannot_replace_pace_md(self):
        text = section(HELP.read_text(encoding="utf-8"), "Switching one on or off")
        self.assertRegex(text, r"cannot replace `Pace\.md`")
        self.assertRegex(text, r"exact line to paste")
        hosts = (PACE_FOLDER / "Product/Help/hosts-and-views.md").read_text(encoding="utf-8")
        self.assertRegex(hosts, r"Copilot[^\n]*cannot replace existing files")

    def test_help_pages_leave_the_choice_of_add_in_file_to_the_index_line(self):
        for page in sorted((PACE_FOLDER / "Product/Help").glob("*.md")):
            with self.subTest(page=page.name):
                self.assertNotIn("ADD-IN.md)", page.read_text(encoding="utf-8").replace("%20", " "))
        hosts = (PACE_FOLDER / "Product/Help/hosts-and-views.md").read_text(encoding="utf-8")
        self.assertIn("(add-ins.md)", hosts)
        self.assertRegex(hosts, r"`Pace\.md` index decides which file")

    def test_help_says_to_remove_the_none_switched_on_line_with_the_first_add_in(self):
        text = section(HELP.read_text(encoding="utf-8"), "Switching one on or off")
        self.assertRegex(text, r"(?i)\bremove\b[^\n]*`None switched on yet\.`")
        self.assertRegex(text, r"last one is switched off, put it back")

    def test_connection_add_ins_assume_no_connection(self):
        for name, source in (("Power BI", "Power BI"), ("Xero", "Xero")):
            with self.subTest(add_in=name):
                text = shipped_add_in(name).read_text(encoding="utf-8")
                first_step = re.search(r"(?m)^1\. (.+)$", section(text, "Steps"))[1]
                self.assertTrue(first_step.startswith("**Check the connection first.**"))
                self.assertIn("Do not assume one exists.", section(text, "What it needs"))
                self.assertIn("**If there is no such connection, say so plainly**", text)
                self.assertIn(f"can't read", text)
                self.assertIn("Do not guess, estimate", text)
                self.assertIn("Never ask for a password or token.", text)
                self.assertIn("It only reads.", section(text, "Limits"))
                self.assertIn(source, text)

    def test_launchers_only_point_to_their_add_in(self):
        for name in CATALOGUE:
            with self.subTest(add_in=name):
                slug = "pace-" + name.lower().replace(" ", "-")
                launchers = list((PACE_FOLDER / SHIPPED / name).rglob("SKILL.md"))
                self.assertEqual(
                    [p.relative_to(PACE_FOLDER / SHIPPED / name) for p in launchers],
                    [Path("Launchers/Claude") / slug / "SKILL.md"],
                )
                match = re.fullmatch(
                    r"---\nname: (?P<name>.+)\ndescription: (?P<description>.+)\n---\n\n(?P<body>.+)\n",
                    launchers[0].read_text(encoding="utf-8"),
                    re.S,
                )
                self.assertIsNotNone(match)
                self.assertEqual(match["name"], slug)
                self.assertTrue(match["description"].startswith(f"Launcher for the {name} add-in"))
                body = match["body"]
                self.assertNotIn("\n", body)
                self.assertLess(len(body), 600)
                self.assertIn("adds no rules of its own", body)
                self.assertIn("`Pace.md`", body)
                self.assertIn(f"`{SHIPPED.as_posix()}/{name}/ADD-IN.md` or the owner's customised copy", body)
                self.assertIn("it is off", body)

    def test_launchers_are_not_discovered_at_startup(self):
        self.assertEqual([p for p in PACE_FOLDER.rglob(".claude") if p.is_dir()], [])
        self.assertEqual(list(PACE_FOLDER.rglob("ADD-IN.md")), list((PACE_FOLDER / SHIPPED).rglob("ADD-IN.md")))


class CustomisedCopyLinkTests(unittest.TestCase):
    """Copy each shipped add-in as add-ins.md documents, then fix its links as documented."""

    @staticmethod
    def documented_link_change():
        text = section(HELP.read_text(encoding="utf-8"), "Customising a shipped add-in")
        step = re.search(r"(?m)^\d+\. [^\n]*links[^\n]*$", text)
        if step is None:
            raise AssertionError("customising steps do not tell the assistant to fix the links")
        old, new = re.findall(r"`([^`]*Help/)`", step[0])[:2]
        return old, new

    def copy_documented(self, folder, name):
        copy = folder.root / MY_ADD_INS / f"{name} - mine"
        shutil.copytree(folder.root / SHIPPED / name, copy)
        return copy

    def test_help_steps_name_the_link_change(self):
        old, new = self.documented_link_change()
        self.assertEqual((old, new), ("../../Help/", "../../Product/Help/"))

    def test_unfixed_copies_lose_their_help_links(self):
        with InventedFolder() as folder:
            copy = self.copy_documented(folder, "Daily brief")
            links = LINK.findall((copy / "ADD-IN.md").read_text(encoding="utf-8"))
            self.assertTrue([link for link in links if not (copy / link).is_file()])

    def test_every_link_in_each_customised_copy_resolves_after_the_documented_change(self):
        old, new = self.documented_link_change()
        for name in CATALOGUE:
            with self.subTest(add_in=name), InventedFolder() as folder:
                copy = self.copy_documented(folder, name)
                add_in = copy / "ADD-IN.md"
                add_in.write_text(add_in.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
                links = LINK.findall(add_in.read_text(encoding="utf-8"))
                self.assertTrue(links)
                for link in links:
                    self.assertTrue((copy / link).resolve().is_file(), link)
                    if "Help/" in link:
                        self.assertEqual((copy / link).resolve(), (folder.root / "Product" / link.split("Product/", 1)[1]).resolve())
                self.assertNotIn(old, add_in.read_text(encoding="utf-8"))
                # Files copied beside ADD-IN.md carry no other relative link; a jump within the same page is not one.
                for other in copy.rglob("*"):
                    if other.is_file() and other != add_in:
                        self.assertNotRegex(other.read_text(encoding="utf-8"), r"\]\(|href=(?!\"#)|src=")

    def test_launchers_in_a_copy_still_point_to_the_index_and_the_index_line_opens_the_copy(self):
        old, new = self.documented_link_change()
        for name in CATALOGUE:
            with self.subTest(add_in=name), InventedFolder() as folder:
                copy = self.copy_documented(folder, name)
                add_in = copy / "ADD-IN.md"
                add_in.write_text(add_in.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
                slug = "pace-" + name.lower().replace(" ", "-")
                launcher = copy / "Launchers/Claude" / slug / "SKILL.md"
                body = launcher.read_text(encoding="utf-8")
                self.assertIn("open `Pace.md`", body)
                self.assertIn("owner's customised copy", body)
                self.assertNotRegex(body, r"\]\(")
                index_path = f"{MY_ADD_INS.as_posix()}/{name} - mine/ADD-IN.md"
                folder.set_index([f"- **{name}** - My own copy. `{index_path}`"])
                chat = Chat(folder.root)
                self.assertEqual(chat.ask(name), Outcome("open", (name,)))
                self.assertEqual(chat.opened[-1], add_in)
                self.assertTrue((folder.root / index_path).is_file())

    def test_every_link_example_in_the_help_resolves_from_a_copy_in_my_add_ins(self):
        """Each "change `A` to `B`" link example: B opens Product/Help from 3 My add-ins/<name>/, A from where the copy was."""
        text = HELP.read_text(encoding="utf-8")
        link_change = re.compile(r"change `(\.\./[^`]*)` to `(\.\./[^`]*)`")
        came_from = {"Customising a shipped add-in": SHIPPED, "Add-ins in an older folder": OLDER_MY_ADD_INS}
        self.assertEqual(len(link_change.findall(text)), len(came_from))  # no example elsewhere goes unchecked
        for heading, source in came_from.items():
            [(old, new)] = link_change.findall(section(text, heading))
            for name in CATALOGUE:
                with self.subTest(section=heading, add_in=name), InventedFolder() as folder:
                    help_folder = (folder.root / "Product/Help").resolve()
                    copy = folder.root / MY_ADD_INS / f"{name} - mine"
                    before = folder.root / source / (name if source == SHIPPED else f"{name} - mine")
                    for place in (copy, before):
                        place.mkdir(parents=True, exist_ok=True)
                    self.assertEqual((copy / new).resolve(), help_folder, new)
                    self.assertEqual((before / old).resolve(), help_folder, old)
                    # Every help link the shipped add-in has opens its page from the copy once changed.
                    shipped_links = LINK.findall(shipped_add_in(name).read_text(encoding="utf-8"))
                    for link in (l for l in shipped_links if l.startswith("../../Help/")):
                        self.assertTrue((copy / ("../../Product/Help/" + link[len("../../Help/"):])).resolve().is_file(), link)

    def test_help_names_the_older_place_only_where_it_explains_older_folders(self):
        text = HELP.read_text(encoding="utf-8")
        rest = text.replace(section(text, "Add-ins in an older folder"), "")
        self.assertNotIn(OLDER_MY_ADD_INS.as_posix(), rest)
        paths = re.findall(r"`([^`]*My add-ins[^`]*)`", rest)
        self.assertTrue(paths)
        for path in paths:
            self.assertTrue(path.startswith(f"{MY_ADD_INS.as_posix()}/"), path)


class OlderFolderTests(unittest.TestCase):
    """A folder that keeps its add-ins in Pace/Add-ins/My add-ins/ keeps working, and so does moving them as documented."""

    @staticmethod
    def move_steps():
        steps = re.findall(r"(?m)^(\d+)\. (.+)$", section(HELP.read_text(encoding="utf-8"), "Add-ins in an older folder"))
        return [step for _, step in steps]

    def older_copy(self, folder, name):
        """A copy customised under the earlier help: in the older place, with that help's link change."""
        copy = folder.root / OLDER_MY_ADD_INS / f"{name} - mine"
        shutil.copytree(folder.root / SHIPPED / name, copy)
        add_in = copy / "ADD-IN.md"
        add_in.write_text(add_in.read_text(encoding="utf-8").replace("../../Help/", "../../../../Product/Help/"), encoding="utf-8")
        return add_in

    def make_older(self, folder):
        shutil.rmtree(folder.root / MY_ADD_INS)
        (folder.root / OLDER_MY_ADD_INS).mkdir(parents=True)
        (folder.root / OLDER_MY_ADD_INS / ".gitkeep").write_bytes(b"")
        pace = folder.root / "Pace.md"
        pace.write_text(pace.read_text(encoding="utf-8").replace(f"`{MY_ADD_INS.as_posix()}/`", f"`{OLDER_MY_ADD_INS.as_posix()}/`"), encoding="utf-8")

    def test_copies_in_the_older_place_keep_opening_and_their_links_resolve(self):
        for name in CATALOGUE:
            with self.subTest(add_in=name), InventedFolder() as folder:
                self.make_older(folder)
                add_in = self.older_copy(folder, name)
                links = LINK.findall(add_in.read_text(encoding="utf-8"))
                self.assertTrue(links)
                for link in links:
                    self.assertTrue((add_in.parent / link).resolve().is_file(), link)
                folder.set_index([f"- **{name}** - My own copy. `{OLDER_MY_ADD_INS.as_posix()}/{name} - mine/ADD-IN.md`"])
                chat = Chat(folder.root)
                self.assertEqual(chat.ask(name), Outcome("open", (name,)))
                self.assertEqual(chat.opened[-1], add_in)

    def test_following_the_move_steps_keeps_every_copy_working(self):
        steps = self.move_steps()
        self.assertEqual(len(steps), 4)
        self.assertIn(f"from `{OLDER_MY_ADD_INS.as_posix()}/` into `{MY_ADD_INS.as_posix()}/`", steps[0])
        [(old_link, new_link)] = re.findall(r"change `(\.\./[^`]*)` to `(\.\./[^`]*)`", steps[1])
        [(old_path, new_path)] = re.findall(r"change `([^`]+)` to `([^`]+)`", steps[2])
        self.assertEqual((old_path, new_path), (f"{OLDER_MY_ADD_INS.as_posix()}/", f"{MY_ADD_INS.as_posix()}/"))
        self.assertIn("`.gitkeep`", steps[3])
        for name in CATALOGUE:
            with self.subTest(add_in=name), InventedFolder() as folder:
                self.make_older(folder)
                self.older_copy(folder, name)
                folder.set_index([f"- **{name}** - My own copy. `{OLDER_MY_ADD_INS.as_posix()}/{name} - mine/ADD-IN.md`"])
                # 1. Move the whole folder, keeping its name.
                (folder.root / MY_ADD_INS).mkdir()
                shutil.move(str(folder.root / OLDER_MY_ADD_INS / f"{name} - mine"), str(folder.root / MY_ADD_INS / f"{name} - mine"))
                # 2. The documented link change.
                add_in = folder.root / MY_ADD_INS / f"{name} - mine" / "ADD-IN.md"
                add_in.write_text(add_in.read_text(encoding="utf-8").replace(old_link, new_link), encoding="utf-8")
                # 3. The documented path change in Pace.md: index line and "Where things belong".
                pace = folder.root / "Pace.md"
                pace.write_text(pace.read_text(encoding="utf-8").replace(old_path, new_path), encoding="utf-8")
                # 4. Only the .gitkeep is left in Pace/, so it can go.
                left = [p.relative_to(folder.root) for p in (folder.root / "Pace").rglob("*") if p.is_file()]
                self.assertEqual(left, [OLDER_MY_ADD_INS / ".gitkeep"])
                shutil.rmtree(folder.root / "Pace")

                text = add_in.read_text(encoding="utf-8")
                self.assertNotIn(old_link, text)
                for link in LINK.findall(text):
                    self.assertTrue((add_in.parent / link).resolve().is_file(), link)
                pace_text = pace.read_text(encoding="utf-8")
                self.assertNotIn("Pace/Add-ins", pace_text)
                self.assertEqual(pace_text, (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8").replace(
                    "None switched on yet.", f"- **{name}** - My own copy. `{MY_ADD_INS.as_posix()}/{name} - mine/ADD-IN.md`"))
                chat = Chat(folder.root)
                self.assertEqual(chat.ask(name), Outcome("open", (name,)))
                self.assertEqual(chat.opened[-1], add_in)


class RoutingTests(unittest.TestCase):
    def test_pace_folder_index_is_empty(self):
        text = (PACE_FOLDER / "Pace.md").read_text(encoding="utf-8")
        self.assertEqual(index_entries(text), [])
        self.assertIn("None switched on yet.", text)
        self.assertIn("No add-in file is opened at the start of a chat", text)
        self.assertIn("its steps apply only to that request", text)
        self.assertNotIn("ADD-IN.md`", text)
        self.assertNotIn("## Steps", text)

    def test_invented_chats_open_no_add_in_at_startup(self):
        setups = {
            "fresh PACE folder": lambda folder: None,
            "everything switched on": lambda folder: folder.switch_on(*CATALOGUE),
            "customised copy": lambda folder: (
                folder.customise("Daily brief", "Daily brief - mine"),
                folder.set_index([
                    f"- **Daily brief** - My own brief. `{MY_ADD_INS.as_posix()}/Daily brief - mine/ADD-IN.md`",
                ]),
            ),
        }
        for label, setup in setups.items():
            with self.subTest(setup=label), InventedFolder() as folder:
                setup(folder)
                chat = Chat(folder.root)
                self.assertEqual(chat.opened, [folder.root / "Pace.md"])
                pace = (folder.root / "Pace.md").read_text(encoding="utf-8")
                for entry in chat.index:
                    self.assertEqual(pace.count(entry.path), 1)
                self.assertNotIn("## Steps", pace)
                self.assertEqual(chat.ask("Morning! Quick one: how do I spell receivable?"), Outcome("none"))
                self.assertEqual(chat.opened, [folder.root / "Pace.md"])

    def test_one_relevant_enabled_add_in_opens_on_demand(self):
        with InventedFolder() as folder:
            folder.switch_on("Daily brief", "Reminders")
            chat = Chat(folder.root)
            self.assertEqual([entry.name for entry in chat.index], ["Daily brief", "Reminders"])
            self.assertEqual(chat.ask("Can I have my daily brief for Invented Bakery?"), Outcome("open", ("Daily brief",)))
            self.assertEqual(chat.opened, [folder.root / "Pace.md", folder.root / shipped_add_in("Daily brief").relative_to(PACE_FOLDER)])
            # An add-in that is off is named, not opened or switched on.
            self.assertEqual(chat.ask("What is cash at bank in Xero for March?"), Outcome("off", ("Xero",)))
            self.assertEqual(len(chat.opened), 2)
            self.assertEqual(Chat(folder.root).index, chat.index)

    def test_customised_copy_wins_over_the_shipped_one(self):
        with InventedFolder() as folder:
            copy = folder.customise("Daily brief", "Daily brief - mine")
            folder.set_index([
                f"- **Daily brief** - Gather what needs me today, client calls first. `{MY_ADD_INS.as_posix()}/Daily brief - mine/ADD-IN.md`",
            ])
            chat = Chat(folder.root)
            self.assertEqual(chat.ask("Daily brief please"), Outcome("open", ("Daily brief",)))
            self.assertEqual(chat.opened[-1], copy)
            self.assertNotIn(folder.root / SHIPPED / "Daily brief/ADD-IN.md", chat.opened)
            self.assertIn("**Customised from:** Daily brief", copy.read_text(encoding="utf-8"))

            # A Product update replaces Product only; the owner's copy and choice stand.
            before = copy.read_bytes()
            shutil.rmtree(folder.root / "Product")
            shutil.copytree(PACE_FOLDER / "Product", folder.root / "Product")
            shipped = folder.root / SHIPPED / "Daily brief/ADD-IN.md"
            shipped.write_text(shipped.read_text(encoding="utf-8") + "\n- Invented newer shipped step.\n", encoding="utf-8")
            chat = Chat(folder.root)
            self.assertEqual(chat.ask("Daily brief please"), Outcome("open", ("Daily brief",)))
            self.assertEqual(chat.opened[-1], copy)
            self.assertEqual(copy.read_bytes(), before)

    def test_same_named_file_elsewhere_never_takes_over(self):
        with InventedFolder() as folder:
            folder.customise("Daily brief", "Daily brief")
            folder.switch_on("Daily brief")
            chat = Chat(folder.root)
            chat.ask("daily brief")
            self.assertEqual(chat.opened[-1], folder.root / SHIPPED / "Daily brief/ADD-IN.md")

    def test_two_fitting_lines_ask_and_a_missing_file_is_named(self):
        with InventedFolder() as folder:
            folder.customise("Daily brief", "Daily brief - mine")
            folder.set_index([
                next(line for line in catalogue_lines() if line.startswith("- **Daily brief** ")),
                f"- **Daily brief** - My own brief. `{MY_ADD_INS.as_posix()}/Daily brief - mine/ADD-IN.md`",
            ])
            chat = Chat(folder.root)
            self.assertEqual(chat.ask("daily brief"), Outcome("ask", ("Daily brief", "Daily brief")))
            self.assertEqual(len(chat.opened), 1)

        with InventedFolder() as folder:
            folder.set_index([f"- **Board notes** - Invented owner add-in. `{MY_ADD_INS.as_posix()}/Board notes/ADD-IN.md`"])
            chat = Chat(folder.root)
            self.assertEqual(chat.ask("board notes"), Outcome("missing", (f"{MY_ADD_INS.as_posix()}/Board notes/ADD-IN.md",)))
            self.assertEqual(len(chat.opened), 1)

    def test_malformed_index_line_is_refused(self):
        with self.assertRaises(ValueError):
            index_entries("## Add-in index\n\n- Daily brief, Product/Pace add-ins/Daily brief/ADD-IN.md\n")


if __name__ == "__main__":
    unittest.main()
