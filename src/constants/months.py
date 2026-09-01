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
