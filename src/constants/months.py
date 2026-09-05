"""Month folder names — defined here and nowhere else.

``ARCHIVE_STANDARD.md`` P3: ``NN. Month``, zero-padded number, dot, space, and
the **fixed English** month name. Never ``strftime("%B")``, which follows the
system locale — a Polish-locale Windows would start writing "07. lipiec" and
every folder it created would sort and match differently from the rest of the
archive.

This is a **leaf module**: it imports nothing at all, so both worlds can reach
it. ``constants.py`` cannot import from ``src.pipeline_stages`` (that package's
``__init__`` imports every stage, and one of them imports ``constants.py`` back
— a cycle), and ``pipeline_stages/legacy.py`` should not have to pay
``constants.py``'s ``PHOTO_BASE_FOLDER`` assertion just to spell "05. May".
A month name belongs to neither module, so it lives in its own.
"""

MONTH_FOLDERS = {
    "01": "01. January",
    "02": "02. February",
    "03": "03. March",
    "04": "04. April",
    "05": "05. May",
    "06": "06. June",
    "07": "07. July",
    "08": "08. August",
    "09": "09. September",
    "10": "10. October",
    "11": "11. November",
    "12": "12. December",
}

# The names above, as a set, for the question "is this a month folder?" -- which
# is how a tool finds the level a parking area lives at (ARCHIVE_STANDARD.md
# section 4.1). Building it from MONTH_FOLDERS rather than spelling the twelve
# again is the whole point of them being here (T8).
MONTH_FOLDER_NAMES = frozenset(MONTH_FOLDERS.values())


def is_month_folder(name: str) -> bool:
    """True when ``name`` is one of the twelve month folder names (P3).

    Exact, case-sensitive and closed: "07. July" is a month folder, "7. July",
    "07. lipiec" and "07.July" are not, and each of the three is a real thing a
    locale-aware or hand-made tool has written into an archive before now.
    """
    return name in MONTH_FOLDER_NAMES


def month_folder_of(path):
    """The month folder at or above ``path``, or None if there is none.

    Walks up rather than counting levels, because how deep a folder sits below
    its month varies -- a leaf day folder is one level down, a sub-event inside
    a group two, a taxonomy subfolder of that sub-event three. What they share
    is that exactly one month folder stands above them all.

    Takes and returns a ``Path``; imports nothing, so both worlds can call it.
    """
    current = path
    while True:
        if is_month_folder(current.name):
            return current
        parent = current.parent
        if parent == current:               # the filesystem root: nothing above
            return None
        current = parent
