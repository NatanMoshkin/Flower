"""Operator manual content — deliberately simple.

Scope rule: only what someone standing at the panel needs. No enum values, no
symbol names, no ST. If a sentence would only make sense to a technician, it
belongs in mn_technician.py instead.

The Hebrew keeps PLC/panel words in Latin where the panel itself shows Latin
(step names such as NOT_HOMED, IDLE, ERR), because the operator has to match
what is on the screen. Everything else is translated.
"""

from mn_render import H, Note, P, Steps, Table, UL, page

RED = '<span class="pb r">RED</span>'
ORG = '<span class="pb o">ORANGE</span>'
GRN = '<span class="pb g">GREEN</span>'
RED_H = '<span class="pb r">אדום</span>'
ORG_H = '<span class="pb o">כתום</span>'
GRN_H = '<span class="pb g">ירוק</span>'
LG = '<span class="lamp g"></span>'
LR = '<span class="lamp r"></span>'


def blocks():
    return [
        # ---------------------------------------------------------------- 1
        H("1 &middot; What this machine does",
          "1 &middot; מה המכונה עושה", anchor="what"),
        P("The robot places a plate in the fixture. The machine then clamps it, "
          "drives the separator pins out, presses the push pins home, and "
          "releases. That whole sequence is <strong>one cycle</strong>. The "
          "robot asks for each cycle; the machine runs it.",
          "הרובוט מניח מגש במתקן. המכונה תופסת אותו, מוציאה את פיני ההפרדה, "
          "לוחצת את פיני הדחיפה, ומשחררת. כל הרצף הזה הוא "
          "<strong>מחזור אחד</strong>. הרובוט מבקש כל מחזור; המכונה מבצעת אותו."),
        P("Your job is to put the machine into a state where the robot is "
          "allowed to ask, and to deal with faults. You do not have to start "
          "each cycle by hand — though you can.",
          "התפקיד שלך הוא להביא את המכונה למצב שבו הרובוט מורשה לבקש, ולטפל "
          "בתקלות. אינך צריך להתחיל כל מחזור ידנית — אך אתה יכול."),

        # ---------------------------------------------------------------- 2
        H("2 &middot; The panel", "2 &middot; לוח ההפעלה", anchor="panel"),
        P("Three buttons, each with a light in it, and two status lamps. "
          "<strong>The colour of the button tells you what it does.</strong>",
          "שלושה לחצנים, בכל אחד נורית, ושתי נוריות מצב. "
          "<strong>צבע הלחצן מלמד מה הוא עושה.</strong>"),
        Table(
            [("Button", "לחצן"), ("In Automatic", "במצב אוטומטי"),
             ("In Manual", "במצב ידני")],
            [[(RED, RED_H),
              ("<strong>Hold 1 second</strong> to STOP the machine.",
               "<strong>החזק שנייה אחת</strong> כדי לעצור את המכונה."),
              ("Hold to move the <strong>grippers</strong> out. Let go and they "
               "come back.",
               "החזק כדי להוציא את <strong>התפסניות</strong>. שחרר והן חוזרות.")],
             [(ORG, ORG_H),
              ("If the red lamp is on: press once to <strong>clear the "
               "fault</strong>.",
               "אם הנורית האדומה דולקת: לחץ פעם אחת כדי "
               "<strong>לאפס את התקלה</strong>."),
              ("Hold to move the <strong>separator pins</strong> out.",
               "החזק כדי להוציא את <strong>פיני ההפרדה</strong>.")],
             [(GRN, GRN_H),
              ("Press once to <strong>START</strong> — the machine homes itself "
               "and is then ready.",
               "לחץ פעם אחת כדי <strong>להתחיל</strong> — המכונה מאפסת את "
               "מקומה ואז מוכנה."),
              ("Hold to move the <strong>push pins</strong> out.",
               "החזק כדי להוציא את <strong>פיני הדחיפה</strong>.")],
             [(ORG + " + " + GRN, ORG_H + " + " + GRN_H),
              ("<strong>Hold both for 1 second</strong> to run one cycle "
               "yourself, instead of waiting for the robot.",
               "<strong>החזק את שניהם שנייה אחת</strong> כדי להריץ מחזור אחד "
               "בעצמך, במקום לחכות לרובוט."),
              ("&mdash;", "&mdash;")]]),
        Note("info", "Why two buttons must be held",
             "מדוע יש להחזיק שני לחצנים",
             "Stopping the machine and starting a cycle are both important, so "
             "they need a deliberate hold. A knock or a brushed sleeve cannot "
             "trigger them. The 1&nbsp;second can be changed on the screen.",
             "עצירת המכונה והתחלת מחזור הן שתי פעולות חשובות, ולכן הן דורשות "
             "החזקה מכוונת. מכה מקרית או שרוול שנתקל אינם יכולים להפעיל אותן. "
             "אפשר לשנות את השנייה במסך."),

        # ---------------------------------------------------------------- 3
        H("3 &middot; Starting production", "3 &middot; התחלת ייצור",
          anchor="start"),
        Steps([
            ("Switch the machine on. The screen shows <code>NOT_HOMED</code> — "
             "this means <em>not ready</em>. Nothing will move.",
             "הדלק את המכונה. המסך מציג <code>NOT_HOMED</code> — כלומר "
             "<em>לא מוכן</em>. שום דבר לא יזוז."),
            ("Make sure the screen is in <strong>Automatic</strong> mode.",
             "ודא שהמסך נמצא במצב <strong>אוטומטי</strong>."),
            (f"The {GRN} button light is <strong>blinking</strong>. That is the "
             "machine asking you to press it.",
             f"נורית הלחצן {GRN_H} <strong>מהבהבת</strong>. זו המכונה מבקשת "
             "שתלחץ עליו."),
            (f"Press {GRN}. The pistons all pull back to their home position "
             "and the screen changes to <code>IDLE</code>.",
             f"לחץ {GRN_H}. כל הבוכנות חוזרות למקומן והמסך משתנה ל<code>IDLE</code>."),
            (f"The green lamp {LG} is now <strong>on steadily</strong>. The "
             "machine is ready and the robot may start sending work.",
             f"הנורית הירוקה {LG} דולקת כעת <strong>באור קבוע</strong>. המכונה "
             "מוכנה והרובוט יכול להתחיל לשלוח עבודה."),
        ]),
        Note("warn", "The machine will not move until you press GREEN",
             "המכונה לא תזוז עד שתלחץ על הירוק",
             "This is deliberate. After power-on, after any time in Manual, and "
             "after a STOP, the machine refuses to run — even if the robot asks "
             "— until a person has pressed START. That is what stops it moving "
             "unexpectedly when nobody is watching.",
             "זה מכוון. לאחר הדלקה, לאחר כל שהות במצב ידני, ולאחר עצירה, "
             "המכונה מסרבת לפעול — גם אם הרובוט מבקש — עד שאדם לחץ על התחלה. "
             "זה מה שמונע ממנה לזוז באופן לא צפוי כשאף אחד לא מסתכל."),

        # ---------------------------------------------------------------- 4
        H("4 &middot; Stopping", "4 &middot; עצירה", anchor="stop"),
        P(f"<strong>Hold the {RED} button for 1 second.</strong> Its light "
          "blinks while you hold it, so you can see the machine is counting. "
          f"When it takes effect the screen goes back to <code>NOT_HOMED</code> "
          "and the green lamp goes out.",
          f"<strong>החזק את הלחצן {RED_H} שנייה אחת.</strong> הנורית שלו מהבהבת "
          "בזמן ההחזקה, כך שאתה רואה שהמכונה מונה. כשהפעולה מתבצעת המסך חוזר "
          "ל<code>NOT_HOMED</code> והנורית הירוקה נכבית."),
        P("This is <strong>not</strong> a fault — nothing is broken, the "
          "machine is simply not allowed to run any more. To start again, press "
          f"{GRN}.",
          "זו <strong>אינה</strong> תקלה — שום דבר לא נשבר, פשוט אין יותר אישור "
          f"למכונה לפעול. כדי להתחיל מחדש, לחץ {GRN_H}."),
        Note("danger", "STOP is not an emergency stop",
             "עצירה אינה עצירת חירום",
             "A cycle already under way finishes its current movement. The "
             "pistons are air-driven and springs pull them back, so cutting "
             "power makes everything retract — but do not rely on the STOP "
             "button to protect hands. Use the machine's emergency stop for "
             "that.",
             "מחזור שכבר בעיצומו ישלים את התנועה הנוכחית. הבוכנות מונעות באוויר "
             "וקפיצים מחזירים אותן, כך שהפסקת חשמל גורמת להכל להתכנס — אך אין "
             "להסתמך על לחצן העצירה כדי להגן על הידיים. לשם כך יש להשתמש "
             "בעצירת החירום של המכונה."),

        # ---------------------------------------------------------------- 5
        H("5 &middot; Reading the lamps", "5 &middot; קריאת הנוריות",
          anchor="lamps"),
        Table(
            [("Lamp", "נורית"), ("Meaning", "משמעות")],
            [[(LG + " green, steady", LG + " ירוקה, קבועה"),
              ("Ready and waiting for the robot.", "מוכנה וממתינה לרובוט.")],
             [(LG + " green, blinking", LG + " ירוקה, מהבהבת"),
              ("A cycle is running.", "מחזור מתבצע.")],
             [(LG + " green, off", LG + " ירוקה, כבויה"),
              ("Not ready: either in Manual, or STOPped, or faulted.",
               "לא מוכנה: או במצב ידני, או שנעצרה, או שיש תקלה.")],
             [(LR + " red, on", LR + " אדומה, דולקת"),
              ("<strong>Fault.</strong> See the next section.",
               "<strong>תקלה.</strong> ראה בסעיף הבא.")],
             [(f"{GRN} button light blinking",
               f"נורית הלחצן {GRN_H} מהבהבת"),
              ("Press me to get ready.", "לחץ עליי כדי להתכונן.")],
             [(f"{RED} button light blinking",
               f"נורית הלחצן {RED_H} מהבהבת"),
              ("You are holding it and the STOP is being counted.",
               "אתה מחזיק אותו והעצירה נמנית.")]]),

        # ---------------------------------------------------------------- 6
        H("6 &middot; If the red lamp comes on",
          "6 &middot; אם הנורית האדומה נדלקת", anchor="fault"),
        P("The machine stopped because something did not reach where it was "
          "expected — usually a piston that did not travel, or a plate that "
          "never arrived. The screen shows a short message saying which step "
          "failed.",
          "המכונה עצרה כי משהו לא הגיע ליעדו — בדרך כלל בוכנה שלא זזה, או מגש "
          "שלא הגיע. המסך מציג הודעה קצרה המציינת איזה שלב נכשל."),
        Steps([
            ("Look at the message on the screen and write it down if this keeps "
             "happening.",
             "הסתכל בהודעה שעל המסך ורשום אותה אם התקלה חוזרת."),
            ("Look at the machine. Is something jammed, is a plate crooked, is "
             "air connected?",
             "הסתכל על המכונה. האם משהו תקוע, האם מגש עקום, האם האוויר מחובר?"),
            (f"If you can see nothing wrong: press {ORG} once. The machine "
             "pulls everything back to home and becomes ready again.",
             f"אם אינך רואה בעיה: לחץ {ORG_H} פעם אחת. המכונה מחזירה את הכל "
             "למקום ושבה להיות מוכנה."),
            ("If something <em>is</em> jammed, do not just reset. Switch the "
             "screen to <strong>Manual</strong> and free it by hand first — see "
             "the next section.",
             "אם משהו <em>כן</em> תקוע, אל תאפס סתם. העבר את המסך למצב "
             "<strong>ידני</strong> ושחרר אותו קודם ביד — ראה בסעיף הבא."),
        ]),
        Note("info", "The robot may reset the fault before you do",
             "הרובוט עלול לאפס את התקלה לפניך",
             "The robot watches the machine and can clear a fault itself, so "
             "the red lamp sometimes goes out on its own after a second or two. "
             "That is normal. If the same fault keeps returning, stop the "
             "machine and investigate rather than letting it retry.",
             "הרובוט עוקב אחר המכונה ויכול לאפס תקלה בעצמו, ולכן לעיתים הנורית "
             "האדומה נכבית מעצמה לאחר שנייה או שתיים. זה נורמלי. אם אותה תקלה "
             "חוזרת שוב ושוב, עצור את המכונה ובדוק במקום לתת לה לנסות שוב."),

        # ---------------------------------------------------------------- 7
        H("7 &middot; Moving things by hand",
          "7 &middot; הזזת חלקים ביד", anchor="manual"),
        P("Switch the screen to <strong>Manual</strong>. Now the three buttons "
          "move pistons directly: each one moves its group out while you hold "
          "it, and the springs pull the group back when you let go.",
          "העבר את המסך למצב <strong>ידני</strong>. כעת שלושת הלחצנים מזיזים "
          "בוכנות ישירות: כל אחד מוציא את הקבוצה שלו כל עוד אתה מחזיק, "
          "והקפיצים מחזירים אותה כשאתה משחרר."),
        UL([(f"{RED} &mdash; the two grippers", f"{RED_H} &mdash; שתי התפסניות"),
            (f"{ORG} &mdash; the three separator pins",
             f"{ORG_H} &mdash; שלושת פיני ההפרדה"),
            (f"{GRN} &mdash; the three push pins",
             f"{GRN_H} &mdash; שלושת פיני הדחיפה")]),
        Note("warn", "Manual mode only",
             "מצב ידני בלבד",
             "The buttons do <strong>not</strong> move pistons while the "
             "machine is in Automatic — not even when it is faulted. That is on "
             "purpose: in Automatic the sequence owns the pistons, and two "
             "things driving the same piston is how equipment gets damaged. "
             "Switch to Manual, do the work, then switch back and press "
             f"{GRN} to get ready again.",
             "הלחצנים <strong>אינם</strong> מזיזים בוכנות כשהמכונה במצב אוטומטי "
             "— גם לא כשיש תקלה. זה מכוון: במצב אוטומטי הרצף הוא הבעלים של "
             "הבוכנות, ושני גורמים המפעילים אותה בוכנה הם הדרך שבה ציוד נהרס. "
             f"עבור למצב ידני, בצע את העבודה, חזור למצב אוטומטי ולחץ {GRN_H} "
             "כדי להתכונן שוב."),

        # ---------------------------------------------------------------- 8
        H("8 &middot; Running a cycle yourself",
          "8 &middot; הרצת מחזור בעצמך", anchor="manualcycle"),
        P(f"From <code>IDLE</code> (green lamp steady), <strong>hold {ORG} and "
          f"{GRN} together for 1 second</strong>. The machine runs exactly one "
          "cycle and returns to ready.",
          f"מ<code>IDLE</code> (נורית ירוקה קבועה), <strong>החזק {ORG_H} "
          f"ו{GRN_H} יחד שנייה אחת</strong>. המכונה מבצעת מחזור אחד בדיוק "
          "וחוזרת למצב מוכן."),
        Note("warn", "Press ORANGE first, then GREEN",
             "לחץ קודם על הכתום, אחר כך על הירוק",
             f"If you press {GRN} first, the machine reads it as START on its "
             "own and simply re-homes instead of running a cycle. No harm done "
             "— just release and try again, orange first.",
             f"אם תלחץ קודם {GRN_H}, המכונה תפרש זאת כלחיצת התחלה בלבד ותאפס "
             "מקום במקום להריץ מחזור. אין נזק — שחרר ונסה שוב, כתום קודם."),

        # ---------------------------------------------------------------- 9
        H("9 &middot; Safety", "9 &middot; בטיחות", anchor="safety"),
        UL([("The pistons are held out by air and pulled back by springs. If "
             "power or air is lost, <strong>everything retracts</strong>. That "
             "is the safe direction, but it means a clamped plate is released.",
             "הבוכנות מוחזקות בחוץ באוויר ומוחזרות בקפיצים. אם נופל מתח או "
             "אוויר, <strong>הכל מתכנס</strong>. זה הכיוון הבטוח, אך משמעותו "
             "שמגש שהיה תפוס משתחרר."),
            ("The grippers and the pins can pinch. Keep hands clear whenever "
             "the green lamp is blinking, and whenever the robot is moving.",
             "התפסניות והפינים יכולים ללחוץ ולפצוע. הרחק ידיים בכל זמן שהנורית "
             "הירוקה מהבהבת, ובכל זמן שהרובוט זז."),
            ("<code>NOT_HOMED</code> on the screen does not mean <em>safe</em>. "
             "It means <em>not allowed to run</em>. The robot can still be "
             "moving.",
             "<code>NOT_HOMED</code> על המסך אינו אומר <em>בטוח</em>. הוא אומר "
             "<em>אין אישור לפעול</em>. הרובוט עדיין עשוי לזוז."),
            ("Only one gripper currently has air. The machine is set up to keep "
             "working on one, so do not assume both are holding.",
             "כרגע רק לתפסנית אחת יש אוויר. המכונה מוגדרת להמשיך לעבוד עם אחת, "
             "לכן אל תניח ששתיהן אוחזות.")]),
        Note("danger", "Use the emergency stop for anything urgent",
             "השתמש בעצירת חירום לכל דבר דחוף",
             f"The {RED} button is a controlled stop that takes a second and "
             "lets the current movement finish. It is not a safety device.",
             f"הלחצן {RED_H} הוא עצירה מבוקרת שלוקחת שנייה ומאפשרת לתנועה "
             "הנוכחית להסתיים. הוא אינו אמצעי בטיחות."),
    ]


def build():
    return page(
        "operator-manual.html",
        "Operator's manual", "מדריך למפעיל",
        "Everything you need to run the machine from the panel. If you are "
        "diagnosing a fault or changing settings, use the "
        '<a href="technician-manual.html">technician manual</a> instead.',
        "כל מה שצריך כדי להפעיל את המכונה מלוח ההפעלה. אם אתה מאתר תקלה או "
        'משנה הגדרות, השתמש ב<a href="technician-manual.html">מדריך הטכנאי</a> '
        "במקום.",
        blocks())
