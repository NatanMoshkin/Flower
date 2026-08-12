"""docs/index.html — the entry point that links everything.

Grouped by whether a document is CURRENT or an ARCHIVED record, because the
folder used to mix the two and that is how a stale page gets read as fact. Every
archived entry says what superseded it.
"""

from mn_render import H, Links, Note, P, ltr, page

LIVE = [
    ("http://127.0.0.1:8765/docs/viewer.html?doc=../docs/plans/log-csv-file.md",
     "CSV log file on the PLC", "קובץ לוג CSV בבקר",
     "The log written to a CSV file on the panel itself, so a record survives a "
     "power cycle with no laptop attached. BUILT AND VERIFIED ON THE PANEL "
     "(phases 0–3). Tick <strong>File log</strong> on the Logs page to enable it — "
     "it is OFF by default — then fetch the file over FTP from "
     + ltr("ftp://&lt;panel-ip&gt;/Logs/") + ". "
     "Needs the local server, like the CLAUDE.md link below.",
     "הלוג נכתב לקובץ CSV בבקר עצמו, כדי שהתיעוד ישרוד כיבוי חשמל ללא מחשב "
     "מחובר. יושם ואומת על הפנל (שלבים 0–3). סמן <strong>File log</strong> "
     "במסך הלוג כדי להפעיל — כברירת מחדל כבוי — ואז הורד את הקובץ ב-FTP מ"
     + ltr("ftp://&lt;panel-ip&gt;/Logs/") + ". "
     "דורש את השרת המקומי, כמו הקישור ל-CLAUDE.md מתחת.",
     "live", "built &amp; verified", "יושם ואומת"),
    ("http://127.0.0.1:8765/docs/viewer.html?doc=../docs/plans/pyhmi-csv-log-handoff.md",
     "HANDOFF: show the CSV log in FlowerPyHmi",
     "העברה: הצגת לוג ה-CSV ב-FlowerPyHmi",
     "The web-HMI half of the file log, still to do. FlowerPyHmi is a SEPARATE "
     "repository, so nothing keeps its symbol contract in step automatically. "
     "Lists the 14 PLC symbols to poll, the routes to add, and the three things "
     "not to get wrong. Every symbol in it was checked against the PLC source.",
     "החצי של ה-HMI לקובץ הלוג, טרם בוצע. FlowerPyHmi הוא מאגר נפרד, "
     "ולכן שום דבר לא מסנכרן את חוזה הסמלים אוטומטית. "
     "המסמך מפרט את 14 הסמלים לקריאה, את הנתיבים להוספה, ושלוש נקודות "
     "שחשוב לא לטעות בהן.",
     "data", "not started", "טרם התחיל"),
    ("http://127.0.0.1:8765/docs/viewer.html?doc=../CLAUDE.md",
     "CLAUDE.md — decisions &amp; open work", "CLAUDE.md — החלטות ועבודה פתוחה",
     "The live source of truth: the TODO list grouped by state, every "
     "architectural decision with its reasoning, and the record of what has and "
     "has not been verified. Rendered from the repository root. "
     "NEEDS THE LOCAL SERVER — double-click serve-docs.bat in the repo root "
     "first, or this link will not resolve.",
     "מקור האמת החי: רשימת המשימות מקובצת לפי מצב, כל החלטה ארכיטקטונית "
     "והנימוקים שלה, והתיעוד של מה אומת ומה לא. מוצג משורש המאגר. "
     "דורש את השרת המקומי — הפעל תחילה serve-docs.bat בשורש המאגר, "
     "אחרת הקישור לא יעבוד.",
     "live", "source of truth", "מקור אמת"),
    ("operator-manual.html",
     "Operator's manual", "מדריך למפעיל",
     "Running the machine from the panel: the three buttons, the lamps, "
     "starting, stopping, and what to do when the red lamp comes on.",
     "הפעלת המכונה מלוח ההפעלה: שלושת הלחצנים, הנוריות, התחלה, עצירה, ומה "
     "לעשות כשהנורית האדומה נדלקת.",
     "live", "start here", "התחל כאן"),
    ("technician-manual.html",
     "Technician's manual", "מדריך לטכנאי",
     "Sequence, error codes, every setting on the AutoMain screen, the IO map, "
     "the robot protocol, diagnostics, and the field deviations you must know "
     "about.",
     "רצף, קודי תקלה, כל הגדרה במסך AutoMain, מפת ה-IO, פרוטוקול הרובוט, "
     "אבחון, והחריגות בשטח שחובה להכיר.",
     "live", "detailed", "מפורט"),
    ("auto-state-machine-current.html",
     "Auto state machine — as built", "מכונת המצבים — כפי שנבנתה",
     "All 19 states with their wire values. Click any state for the exact "
     "commands it drives and what each push button does there.",
     "כל 19 המצבים עם ערכי התקשורת שלהם. לחץ על מצב כדי לראות את הפקודות "
     "המדויקות שהוא מפעיל ומה כל לחצן עושה שם.",
     "live", "reference", "עיון"),
    ("pb-test-report.html",
     "Push-button test report", "דוח בדיקת לחצנים",
     "Latest automated run against a live PLC — 58 checks over ADS covering "
     "every button in every machine state.",
     "ההרצה האוטומטית האחרונה מול PLC פעיל — 58 בדיקות דרך ADS המכסות כל לחצן "
     "בכל מצב של המכונה.",
     "live", "test result", "תוצאת בדיקה"),
    ("bench-checklist-arming.html",
     "Bench &amp; field checklist", "רשימת בדיקות שולחן ושדה",
     "What has been verified and what has not. The outstanding field checks and "
     "the pre-machine steps live here.",
     "מה אומת ומה לא. בדיקות השדה הפתוחות והשלבים שלפני העלייה למכונה נמצאים "
     "כאן.",
     "live", "open items", "פתוח"),
    ("167_01_SAAD_PinPush_IO_List.xlsx",
     "IO list (spreadsheet)", "רשימת IO (גיליון)",
     "The authority for the channel map — sheet IO, column NEW. The "
     "GVL_IO..[] column is the OLD pre-rewire numbering; do not read it by "
     "mistake.",
     "מקור הסמכות למפת הערוצים — גיליון IO, עמודה NEW. העמודה GVL_IO..[] היא "
     "המספור הישן שלפני החיווט מחדש; אל תקרא אותה בטעות.",
     "data", "source of truth", "מקור אמת"),
]

ARCHIVE = [
    ("archive/auto-state-machine-pause.html",
     "Pause / Continue proposal", "הצעת השהיה / המשך",
     "REJECTED 2026-08-05 — never implemented. Kept for one finding that still "
     "governs any future attempt: spring-return pistons cannot be stopped "
     "mid-stroke.",
     "נדחה ב-2026-08-05 — לא יושם. נשמר בשל מסקנה אחת שעדיין תקפה לכל ניסיון "
     "עתידי: לא ניתן לעצור בוכנות עם חזרה בקפיץ באמצע התנועה.",
     "archive", "rejected", "נדחה"),
    ("archive/auto-state-machine-retract-all.html",
     "Retract-all split from ERR", "הפרדת ההכנסה ממצב תקלה",
     "PARTLY IMPLEMENTED — the RECOVER_* chain shipped. The retry counter and "
     "the reset-ownership split did not: the robot only sends its reset when a "
     "human presses a button on its own panel, so the premise was wrong.",
     "יושם חלקית — שרשרת RECOVER_* נכנסה. מונה הניסיונות והפרדת בעלות האיפוס "
     "לא: הרובוט שולח איפוס רק כאשר אדם לוחץ לחצן בלוח שלו, ולכן ההנחה הייתה "
     "שגויה.",
     "archive", "partly", "חלקית"),
    ("archive/auto-state-machine-combined.html",
     "Combined target proposal", "הצעה משולבת",
     "SUPERSEDED — three of its four proposals changed before implementation. "
     "Read the as-built diagram instead.",
     "הוחלף — שלוש מארבע ההצעות שבו שונו לפני היישום. קרא את תרשים כפי שנבנתה "
     "במקום.",
     "archive", "superseded", "הוחלף"),
    ("archive/operator-manual.md",
     "Operator manual (old, Markdown)", "מדריך מפעיל (ישן, Markdown)",
     "Superseded by the HTML operator manual above. Predates the arming model, "
     "so it describes a start sequence the machine no longer has.",
     "הוחלף על ידי מדריך המפעיל ב-HTML שלמעלה. קדם למודל האישור, ולכן מתאר רצף "
     "התחלה שאינו קיים יותר במכונה.",
     "archive", "superseded", "הוחלף"),
    ("archive/configuration.html",
     "Configuration reference (old)", "מדריך תצורה (ישן)",
     "Snapshot from 2026-07-27. Predates the arming model, the recovery chain "
     "and the new button behaviour. The technician manual replaces it.",
     "תצלום מ-2026-07-27. קדם למודל האישור, לשרשרת השחזור ולהתנהגות הלחצנים "
     "החדשה. מדריך הטכנאי מחליף אותו.",
     "archive", "stale", "מיושן"),
    ("archive/operation.html",
     "Operation &amp; install guide (old)", "מדריך הפעלה והתקנה (ישן)",
     "Snapshot from 2026-07-27, same vintage and same problem.",
     "תצלום מ-2026-07-27, מאותה תקופה ועם אותה בעיה.",
     "archive", "stale", "מיושן"),
    ("archive/open-issues.html",
     "Open issues (old)", "נושאים פתוחים (ישן)",
     "Snapshot from 2026-07-27. The live list of open items is the TODO section "
     "of CLAUDE.md in the repository root.",
     "תצלום מ-2026-07-27. הרשימה החיה של נושאים פתוחים היא מקטע ה-TODO בקובץ "
     "CLAUDE.md בשורש המאגר.",
     "archive", "stale", "מיושן"),
    ("archive/robot-integration-options.md",
     "Robot integration options", "אפשרויות שילוב הרובוט",
     "The four architectures considered in July 2026. Resolved: TCP-only. Kept "
     "for archaeology; it does not describe current behaviour.",
     "ארבע הארכיטקטורות שנשקלו ביולי 2026. הוכרע: TCP בלבד. נשמר לצורכי "
     "היסטוריה; אינו מתאר את ההתנהגות הנוכחית.",
     "archive", "historic", "היסטורי"),
]


def blocks():
    return [
        H("Current documents", "מסמכים עדכניים", anchor="live"),
        P("These describe the machine as it runs today.",
          "אלה מתארים את המכונה כפי שהיא פועלת היום."),
        Links(LIVE),

        H("Archive", "ארכיון", anchor="archive"),
        P("Kept for the reasoning and the decision trail. <strong>Do not treat "
          "any of these as a description of the current machine.</strong> Each "
          "entry says what replaced it.",
          "נשמרים בשל הנימוקים ושרשרת ההחלטות. <strong>אל תתייחס לאף אחד מהם "
          "כתיאור המכונה הנוכחית.</strong> כל רשומה מציינת מה החליף אותה."),
        Links(ARCHIVE),

        H("Where the live source of truth is", "היכן מקור האמת החי",
          anchor="truth"),
        Note("info", "CLAUDE.md in the repository root",
             "CLAUDE.md בשורש המאגר",
             "The open-issues list, every architectural decision and its "
             "reasoning, and the record of what has and has not been verified "
             "all live there. It is maintained with the code, so it does not go "
             "stale the way a snapshot page does. The HTML here is generated "
             "from it and from the PLC source.",
             "רשימת הנושאים הפתוחים, כל החלטה ארכיטקטונית והנימוקים שלה, "
             "והתיעוד של מה אומת ומה לא — כולם נמצאים שם. הוא מתוחזק יחד עם "
             "הקוד, ולכן אינו מתיישן כמו דף תצלום. ה-HTML שכאן נוצר ממנו "
             "ומקוד ה-PLC."),
        P("Regenerate these pages with "
          "<code>python scripts/manuals/build_manuals.py</code> and "
          "<code>python scripts/statediagram/build_state_diagrams.py</code>. "
          "Edit the content modules under <code>scripts/</code>, never the "
          "generated HTML.",
          "צור מחדש את הדפים האלה עם "
          "<code>python scripts/manuals/build_manuals.py</code> ועם "
          "<code>python scripts/statediagram/build_state_diagrams.py</code>. "
          "ערוך את מודולי התוכן תחת <code>scripts/</code>, לעולם לא את "
          "ה-HTML שנוצר."),
    ]


def build():
    return page(
        "index.html",
        "Documentation", "תיעוד",
        "Everything for the 167_01 pin-push assembly stand. Current documents "
        "first; superseded ones are in the archive with a note saying what "
        "replaced them.",
        "כל התיעוד עבור מתקן ההרכבה " + ltr("167_01") + ". מסמכים עדכניים תחילה; מסמכים שהוחלפו "
        "נמצאים בארכיון עם הערה המציינת מה החליף אותם.",
        blocks())
