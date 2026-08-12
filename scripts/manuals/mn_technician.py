"""Technician manual content — the detailed document.

Everything here is transcribed from the source of record: FB_MasterAutoCycle,
MAIN, PRG_IoMap, the DUTs, and docs/167_01_SAAD_PinPush_IO_List.xlsx (sheet IO,
column NEW). Where the machine deviates from its own documentation, the
deviation is stated rather than smoothed over -- a technician chasing a fault
needs the truth, not the intent.

Hebrew keeps all identifiers, step names and error codes in Latin. A technician
cross-references these against the panel and the source, so translating them
would be actively harmful.
"""

from mn_render import H, Note, P, Steps, Table, UL, ltr, page


def blocks():
    return [
        # ---------------------------------------------------------------- 1
        H("1 &middot; System overview", "1 &middot; סקירת המערכת",
          anchor="overview"),
        P("One device does everything: a Beckhoff <strong>CP6606</strong> panel "
          "PC running TwinCAT 3. It holds the PLC program and the operator "
          "screens (classic PLC visualization). There is no separate HMI box "
          "and no PC in the loop.",
          "מכשיר אחד עושה הכל: פאנל <strong>CP6606</strong> של Beckhoff המריץ "
          "TwinCAT 3. הוא מכיל את תוכנית ה-PLC ואת מסכי המפעיל (ויזואליזציה "
          "קלאסית). אין קופסת HMI נפרדת ואין מחשב בלופ."),
        Table(
            [("Part", "חלק"), ("What it is", "מה זה")],
            [[("<code>MAIN</code>", "<code>MAIN</code>"),
              ("Runs every scan. Forces the machine mode onto all eight "
               "pistons, reads the push buttons, drives the lamps, and "
               "translates the robot's commands.",
               "רץ בכל סריקה. כופה את מצב המכונה על שמונה הבוכנות, קורא את "
               "הלחצנים, מפעיל את הנוריות, ומתרגם את פקודות הרובוט.")],
             [("<code>FB_MasterAutoCycle</code>", "<code>FB_MasterAutoCycle</code>"),
              ("The sequence. One state machine, 19 assigned states.",
               "הרצף. מכונת מצבים אחת, 19 מצבים.")],
             [("<code>FB_SolSpringPiston_2Pos</code>",
               "<code>FB_SolSpringPiston_2Pos</code>"),
              ("One instance per actuator, eight in total. Single coil, spring "
               "return.",
               "מופע אחד לכל מפעיל, שמונה בסך הכל. סליל אחד, חזרה בקפיץ.")],
             [("<code>PRG_IoMap</code>", "<code>PRG_IoMap</code>"),
              ("Copies raw IO to named aliases. Runs on its own 5&nbsp;ms task, "
               "which pre-empts the 10&nbsp;ms PLC task.",
               "מעתיק IO גולמי לשמות. רץ במשימה נפרדת של 5&nbsp;מ\"ש, הקודמת "
               "למשימת ה-PLC של 10&nbsp;מ\"ש.")],
             [("<code>FB_RobotTcpClient</code>", "<code>FB_RobotTcpClient</code>"),
              ("The PLC is the TCP <em>client</em>; the robot is the server on "
               "port 6001.",
               "ה-PLC הוא <em>לקוח</em> TCP; הרובוט הוא השרת בפורט 6001.")]]),
        Note("info", "All eight actuators are single-coil spring-return",
             "כל שמונה המפעילים הם חד-סליליים עם חזרה בקפיץ",
             "Energising the coil drives the piston out; de-energising lets a "
             "spring pull it home. There is no mid-position and no brake. Power "
             "loss, a broken wire or a dead coil all retract — fail-safe by "
             "construction. It also means a piston cannot be stopped part-way, "
             "which rules out several otherwise-obvious features.",
             "הפעלת הסליל מוציאה את הבוכנה; ניתוקו מאפשר לקפיץ להחזירה. אין "
             "מצב אמצע ואין בלם. נפילת מתח, חוט קרוע או סליל מקולקל — כולם "
             "מכניסים את הבוכנה. זהו כשל-לבטוח מעצם הבנייה. משמעות נוספת: לא "
             "ניתן לעצור בוכנה באמצע התנועה, מה ששולל כמה תכונות מובנות מאליהן."),

        # ---------------------------------------------------------------- 2
        H("2 &middot; The Auto sequence", "2 &middot; רצף האוטומט",
          anchor="sequence"),
        P('The full picture, clickable state by state, is in '
          '<a href="auto-state-machine-current.html">the as-built state machine '
          "diagram</a>. Summary:",
          'התמונה המלאה, מצב אחר מצב עם לחיצה, נמצאת ב'
          '<a href="auto-state-machine-current.html">תרשים מכונת המצבים כפי '
          "שנבנתה</a>. תמצית:"),
        Table(
            [("State", "מצב"), ("Value", "ערך"), ("What happens", "מה קורה")],
            [[("<code>NOT_HOMED</code>", "<code>NOT_HOMED</code>"), ("40", "40"),
              ("In Automatic but <strong>not armed</strong>. Nothing driven, no "
               "timer. The power-up state, and where STOP and Manual leave the "
               "machine. Only an operator START leaves it.",
               "במצב אוטומטי אך <strong>ללא אישור</strong>. שום דבר לא מופעל, "
               "אין טיימר. זהו מצב ההדלקה, ולשם מגיעים לאחר עצירה או מצב ידני. "
               "רק לחיצת התחלה של מפעיל מוציאה ממנו.")],
             [("<code>IDLE</code>", "<code>IDLE</code>"), ("0", "0"),
              ("Armed. Waits for the robot's <code>CMD:1</code>, or the "
               "operator's two-button hold.",
               "מאושר. ממתין ל<code>CMD:1</code> מהרובוט, או להחזקת שני "
               "הלחצנים על ידי המפעיל.")],
             [("<code>INIT_PUSH/SEP/GRIP_RETRACTING</code>",
               "<code>INIT_PUSH/SEP/GRIP_RETRACTING</code>"),
              ("10 / 11 / 12", "10 / 11 / 12"),
              ("The retract chain: push home, then sep, then grip. Ordering "
               "matters — it is a collision constraint. Exits to "
               "<code>IDLE</code> when arming, or to <code>CHECK_PLATE</code> "
               "when it is the front of a cycle.",
               "שרשרת ההכנסה: קודם דחיפה, אחר כך הפרדה, אחר כך תפיסה. הסדר "
               "חשוב — זו מניעת התנגשות. יוצא ל<code>IDLE</code> בעת אישור, או "
               "ל<code>CHECK_PLATE</code> כשזו תחילת מחזור.")],
             [("<code>CHECK_PLATE</code>", "<code>CHECK_PLATE</code>"),
              ("20", "20"),
              ("Waits for the plate. Was called <code>WAIT_PLATE</code>; "
               "renamed 2026-08-05, <strong>wire value unchanged</strong>.",
               "ממתין למגש. נקרא בעבר <code>WAIT_PLATE</code>; שונה השם "
               "ב-2026-08-05, <strong>ערך התקשורת לא שונה</strong>.")],
             [("<code>GRIP_EXTENDING</code> &rarr; <code>GRIP_RETRACTING</code>",
               "<code>GRIP_EXTENDING</code> &rarr; <code>GRIP_RETRACTING</code>"),
              ("21, 1, 3, 4, 5, 6, 7, 8, 22", "21, 1, 3, 4, 5, 6, 7, 8, 22"),
              ("The cycle: clamp, sep out, push out, dwell, push back, dwell, "
               "sep back, dwell, release. Then <code>IDLE</code>, still armed.",
               "המחזור: תפיסה, הוצאת הפרדה, הוצאת דחיפה, השהיה, החזרת דחיפה, "
               "השהיה, החזרת הפרדה, השהיה, שחרור. אחר כך <code>IDLE</code>, "
               "עדיין מאושר.")],
             [("<code>ERR</code>", "<code>ERR</code>"), ("99", "99"),
              ("Latched. Only RESET leaves it — HMI button, orange PB2, or the "
               "robot's <code>CMD:2</code>.",
               "נעול. רק איפוס מוציא ממנו — לחצן במסך, לחצן כתום, או "
               "<code>CMD:2</code> מהרובוט.")],
             [("<code>RECOVER_PUSH/SEP/GRIP_RETR</code>",
               "<code>RECOVER_PUSH/SEP/GRIP_RETR</code>"),
              ("50 / 51 / 52", "50 / 51 / 52"),
              ("<strong>Fault recovery only.</strong> Same motion as the INIT "
               "chain but its own identity, so a failed recovery reports "
               "12/13/14 instead of looking like a failed arming. Always exits "
               "to <code>IDLE</code>.",
               "<strong>שחזור מתקלה בלבד.</strong> אותה תנועה כמו שרשרת "
               "ההכנסה אך בזהות נפרדת, כך ששחזור שנכשל מדווח " + ltr("12/13/14") + " ולא נראה "
               "כמו אישור שנכשל. יוצא תמיד ל<code>IDLE</code>.")]]),
        Note("ok", "Two kinds of start, different owners",
             "שני סוגי התחלה, בעלים שונים",
             "<strong>Operator START</strong> (HMI button or green PB3) means "
             "<em>home the pistons and arm</em> — it never runs a cycle. "
             "<strong>Robot <code>CMD:1</code></strong> means <em>run one "
             "cycle</em>, and is only accepted from <code>IDLE</code>. The "
             "operator's two-button hold is fed into the same input as "
             "<code>CMD:1</code>, because it means the same thing.",
             "<strong>התחלה של מפעיל</strong> (לחצן במסך או לחצן ירוק) פירושה "
             "<em>אפס מקום ואשר</em> — היא לעולם אינה מריצה מחזור. "
             "<strong><code>CMD:1</code> מהרובוט</strong> פירושו <em>הרץ מחזור "
             "אחד</em>, ומתקבל רק מ<code>IDLE</code>. החזקת שני הלחצנים של "
             "המפעיל מוזנת לאותה כניסה כמו <code>CMD:1</code>, כי משמעותה זהה."),

        # ---------------------------------------------------------------- 3
        H("3 &middot; Error codes", "3 &middot; קודי תקלה", anchor="errors"),
        Table(
            [("Code", "קוד"), ("Step that timed out", "השלב שפג זמנו")],
            [[("1 / 3 / 4 / 5", "1 / 3 / 4 / 5"),
              ("SEP_EXTENDING / PUSH_EXTENDING / PUSH_RETRACTING / SEP_RETRACTING",
               "SEP_EXTENDING / PUSH_EXTENDING / PUSH_RETRACTING / SEP_RETRACTING")],
             [("6 / 7 / 8", "6 / 7 / 8"),
              ("The three <code>INIT_*</code> steps — <strong>arming</strong>",
               "שלושת שלבי <code>INIT_*</code> — <strong>אישור</strong>")],
             [("9", "9"),
              ("<code>CHECK_PLATE</code> — plate never arrived. Suppressed by "
               "<code>bBypassPlateSensors</code>.",
               "<code>CHECK_PLATE</code> — המגש לא הגיע. מבוטל על ידי "
               "<code>bBypassPlateSensors</code>.")],
             [("10 / 11", "10 / 11"),
              ("GRIP_EXTENDING / GRIP_RETRACTING",
               "GRIP_EXTENDING / GRIP_RETRACTING")],
             [("12 / 13 / 14", "12 / 13 / 14"),
              ("The three <code>RECOVER_*</code> steps — "
               "<strong>recovery</strong>. Deliberately distinct from 6/7/8 so "
               "you can tell which one failed.",
               "שלושת שלבי <code>RECOVER_*</code> — <strong>שחזור</strong>. "
               "נפרדים במתכוון מ-" + ltr("6/7/8") + " כדי שתוכל לדעת מי נכשל.")],
             [("2 and 99", "2 ו-99"),
              ("<strong>Retired, never set.</strong> Do not reuse the numbers — "
               "old logs and CSV exports still carry them.",
               "<strong>הוצאו משימוש, לא נקבעים.</strong> אל תעשה בהם שימוש "
               "חוזר — יומנים וקבצי CSV ישנים עדיין מכילים אותם.")]]),
        Note("danger", "With bNoSensors set, almost no error can occur",
             "כאשר bNoSensors מסומן, כמעט שום תקלה לא יכולה לקרות",
             "<code>bNoSensors</code> makes the twelve movement steps advance on "
             "their timer instead of on sensors, so codes "
             "1/3/4/5/6/7/8/10/11/12/13/14 all become <strong>unreachable</strong> "
             "— only code 9 can still fire. Every bench test so far has run with "
             "this flag set, which means <strong>no movement-timeout path has "
             "ever been exercised on any panel.</strong> Turn it off before "
             "production.",
             "<code>bNoSensors</code> גורם לשנים-עשר שלבי התנועה להתקדם לפי "
             "הטיימר במקום לפי חיישנים, כך שהקודים "
             "1/3/4/5/6/7/8/10/11/12/13/14 הופכים <strong>בלתי ניתנים "
             "להשגה</strong> — רק קוד 9 עוד יכול לקרות. כל הבדיקות עד כה רצו עם "
             "דגל זה מסומן, כלומר <strong>אף מסלול פסק-זמן של תנועה לא נבדק "
             "מעולם באף פאנל.</strong> כבה אותו לפני ייצור."),

        # ---------------------------------------------------------------- 4
        H("4 &middot; Settings on the AutoMain screen",
          "4 &middot; הגדרות במסך AutoMain", anchor="settings"),
        Table(
            [("Field", "שדה"), ("Default", "ברירת מחדל"), ("Meaning", "משמעות")],
            [[("<code>tStepTimeoutMs</code>", "<code>tStepTimeoutMs</code>"),
              ("10000", "10000"),
              ("Movement budget for all twelve motion steps. Expiry = fault.",
               "תקציב זמן לשנים-עשר שלבי התנועה. פקיעה = תקלה.")],
             [("<code>tPlateWaitTimeoutMs</code>",
               "<code>tPlateWaitTimeoutMs</code>"), ("10000", "10000"),
              ("How long <code>CHECK_PLATE</code> waits for the robot to place "
               "the plate.",
               "כמה זמן <code>CHECK_PLATE</code> ממתין שהרובוט יניח את המגש.")],
             [("<code>tDwellPushMs</code>", "<code>tDwellPushMs</code>"),
              ("2000", "2000"),
              ("How long the push pins are held loaded.",
               "כמה זמן פיני הדחיפה מוחזקים בעומס.")],
             [("<code>tPushRetractedDwellMs</code> / "
               "<code>tSepRetractedDwellMs</code>",
               "<code>tPushRetractedDwellMs</code> / "
               "<code>tSepRetractedDwellMs</code>"), ("500 / 500", "500 / 500"),
              ("Settle pauses after each retract.",
               "השהיות התייצבות אחרי כל הכנסה.")],
             [("<code>tPbStopHoldMs</code>", "<code>tPbStopHoldMs</code>"),
              ("1000", "1000"),
              ("How long red PB1 must be held to STOP.",
               "כמה זמן להחזיק את הלחצן האדום כדי לעצור.")],
             [("<code>tPbStartHoldMs</code>", "<code>tPbStartHoldMs</code>"),
              ("1000", "1000"),
              ("How long orange + green must be held to run one cycle.",
               "כמה זמן להחזיק כתום + ירוק כדי להריץ מחזור אחד.")],
             [("<code>bNoSensors</code>", "<code>bNoSensors</code>"),
              ("FALSE", "FALSE"),
              ("<strong>Bench only.</strong> Steps advance on time, not "
               "sensors. See the warning above.",
               "<strong>לשולחן עבודה בלבד.</strong> שלבים מתקדמים לפי זמן, לא "
               "לפי חיישנים. ראה אזהרה לעיל.")],
             [("<code>bBypassPlateSensors</code>",
               "<code>bBypassPlateSensors</code>"), ("FALSE", "FALSE"),
              ("Removes the <code>CHECK_PLATE</code> <em>error</em> only, not "
               "the wait. The timeout becomes a fixed placement dwell.",
               "מבטל רק את <em>התקלה</em> של <code>CHECK_PLATE</code>, לא את "
               "ההמתנה. פסק-הזמן הופך להשהיית הנחה קבועה.")],
             [("<code>bAutoMode</code>", "<code>bAutoMode</code>"),
              ("FALSE", "FALSE"),
              ("Automatic / Manual. The single source of truth for every "
               "piston's mode — no per-piston override exists.",
               "אוטומטי / ידני. מקור האמת היחיד למצב כל בוכנה — אין דריסה "
               "פרטנית לבוכנה.")]]),
        Note("warn", "These survive a power cycle — including the bench flags",
             "אלה נשמרים לאחר כיבוי — כולל דגלי השולחן",
             "The settings are persistent and are flushed to disk about two "
             "seconds after you stop editing. That includes "
             "<code>bNoSensors</code> and <code>bBypassPlateSensors</code>: a "
             "flag left on for a bench session <strong>comes back on after a "
             "reboot</strong>. Check both before running production.",
             "ההגדרות נשמרות ונכתבות לדיסק כשתי שניות לאחר סיום העריכה. זה כולל "
             "את <code>bNoSensors</code> ואת <code>bBypassPlateSensors</code>: "
             "דגל שהושאר דלוק לבדיקה <strong>יחזור דלוק לאחר אתחול</strong>. "
             "בדוק את שניהם לפני ייצור."),

        # ---------------------------------------------------------------- 5
        H("5 &middot; Robot interface", "5 &middot; ממשק הרובוט",
          anchor="robot"),
        P("Raw ASCII over TCP, no newline framing, one send &rarr; one reply. "
          "The PLC dials the robot; the endpoint is editable on the Robot "
          "screen.",
          "ASCII גולמי מעל TCP, בלי מפריד שורה, שליחה אחת &rarr; תשובה אחת. "
          "ה-PLC מתקשר לרובוט; ניתן לערוך את הכתובת במסך הרובוט."),
        Table(
            [("PLC sends", "ה-PLC שולח"), ("Robot replies", "הרובוט משיב"),
             ("Meaning", "משמעות")],
            [[("<code>STATE:0</code>", "<code>STATE:0</code>"),
              ("<code>CMD:1</code>", "<code>CMD:1</code>"),
              ("Armed — run one cycle.", "מאושר — הרץ מחזור אחד.")],
             [("<code>STATE:99</code>", "<code>STATE:99</code>"),
              ("<code>CMD:2</code>", "<code>CMD:2</code>"),
              ("Faulted — reset it.", "תקלה — אפס אותה.")],
             [("anything else", "כל דבר אחר"),
              ("<code>CMD:0</code>", "<code>CMD:0</code>"),
              ("Wait. This is why new states cost nothing robot-side: 30, 40, "
               "50, 51, 52 all land here.",
               "המתן. זו הסיבה שמצבים חדשים אינם עולים דבר בצד הרובוט: "
               + ltr("30, 40, 50, 51, 52") + " — כולם נופלים לכאן.")]]),
        Note("warn", "The step numbers are a wire contract",
             "מספרי המצבים הם חוזה תקשורת",
             "<code>eStep</code>'s numeric value goes on the wire, so a state "
             "may be <em>renamed</em> freely but <strong>never "
             "renumbered</strong>. <code>0</code> and <code>99</code> in "
             "particular <em>are</em> the protocol.",
             "הערך המספרי של <code>eStep</code> נשלח בתקשורת, ולכן ניתן "
             "<em>לשנות שם</em> של מצב בחופשיות אך <strong>לעולם לא את "
             "המספר</strong>. במיוחד <code>0</code> ו<code>99</code> — הם "
             "עצמם הפרוטוקול."),

        # ---------------------------------------------------------------- 6
        H("6 &middot; IO map", "6 &middot; מפת כניסות ויציאות", anchor="io"),
        P("Authority is <code>docs/167_01_SAAD_PinPush_IO_List.xlsx</code>, "
          "sheet <code>IO</code>, column <strong>NEW</strong> — the as-rewired "
          "assignment. The <code>GVL_IO..[]</code> column in that sheet is the "
          "<em>old</em> numbering; do not read it by mistake.",
          "מקור הסמכות הוא <code>docs/167_01_SAAD_PinPush_IO_List.xlsx</code>, "
          "גיליון <code>IO</code>, עמודה <strong>NEW</strong> — החיווט לאחר "
          "השינוי. העמודה <code>GVL_IO..[]</code> באותו גיליון היא המספור "
          "<em>הישן</em>; אל תקרא אותה בטעות."),
        Table(
            [("Device", "התקן"), ("DI retract", "כניסה מוכנס"),
             ("DI extend", "כניסה מוצא"), ("DO", "יציאה"), ("Status", "מצב")],
            [[("SepSol1 / 2 / 3", "SepSol1 / 2 / 3"), ("3 / 7 / 11", "3 / 7 / 11"),
              ("4 / 8 / 12", "4 / 8 / 12"), ("4 / 5 / 6", "4 / 5 / 6"),
              ("ok", "תקין")],
             [("PushSol1 / 2 / 3", "PushSol1 / 2 / 3"), ("1 / 5 / 9", "1 / 5 / 9"),
              ("2 / 6 / 10", "2 / 6 / 10"), ("1 / 2 / 3", "1 / 2 / 3"),
              ("ok", "תקין")],
             [("PB1 red / PB2 orange / PB3 green",
               "לחצן אדום / כתום / ירוק"),
              ("13 / 14 / 15", "13 / 14 / 15"), ("&mdash;", "&mdash;"),
              ("7 / 8 / 9 (LEDs)", ltr("7 / 8 / 9") + " (נוריות)"), ("ok", "תקין")],
             [("GripSolL", "GripSolL"), ("17", "17"), ("18", "18"), ("10", "10"),
              ("ok", "תקין")],
             [("GripSolR", "GripSolR"), ("19", "19"), ("20", "20"), ("11", "11"),
              ("<strong>NO AIR</strong>; both sensors unconfirmed",
               "<strong>אין אוויר</strong>; שני החיישנים לא אומתו")],
             [("Plate sensors", "חיישני מגש"), ("21, 22", "21, 22"),
              ("&mdash;", "&mdash;"), ("&mdash;", "&mdash;"),
              ("21 ok; 22 unconfirmed. <strong>L/R swapped</strong> — see below.",
               "21 תקין; 22 לא אומת. <strong>ימין/שמאל הפוכים</strong> — ראה להלן.")],
             [("Status lamps green / red", "נוריות מצב ירוקה / אדומה"),
              ("&mdash;", "&mdash;"), ("&mdash;", "&mdash;"), ("12 / 13", "12 / 13"),
              ("ok", "תקין")]]),
        P("Sep and Push are <strong>interleaved on the input side</strong> and "
          "<strong>swapped on the output side</strong>. That is the physical "
          "wiring, not a mistake to tidy up.",
          "הפרדה ודחיפה <strong>משולבים בצד הכניסות</strong> "
          "ו<strong>מוחלפים בצד היציאות</strong>. זהו החיווט הפיזי, לא טעות "
          "שצריך לסדר."),

        # ---------------------------------------------------------------- 7
        H("7 &middot; Known deviations", "7 &middot; חריגות ידועות",
          anchor="deviations"),
        Note("danger", "Grip and plate use OR, not AND",
             "תפיסה ומגש משתמשים ב-OR, לא ב-AND",
             "Because <code>GripSolR</code> has no air, the sequence advances "
             "when <strong>either</strong> gripper reports position, and the "
             "plate gate passes on <strong>either</strong> sensor. This is a "
             "deliberate decision to keep producing on one gripper. The cost: a "
             "genuine failure of one gripper is <strong>invisible</strong>, and "
             "errors 10/11 can only fire when <em>both</em> fail. Treat grip "
             "position as unverified in any fault analysis.",
             "מכיוון שאין אוויר ל<code>GripSolR</code>, הרצף מתקדם כאשר "
             "<strong>אחת</strong> מהתפסניות מדווחת על מקום, ושער המגש עובר עם "
             "<strong>אחד</strong> מהחיישנים. זו החלטה מכוונת כדי להמשיך לייצר "
             "עם תפסנית אחת. המחיר: כשל אמיתי של תפסנית אחת הוא "
             "<strong>בלתי נראה</strong>, וקודי 10/11 יכולים לקרות רק כאשר "
             "<em>שתיהן</em> נכשלות. התייחס למצב התפיסה כלא מאומת בכל ניתוח "
             "תקלה."),
        Note("warn", "Plate sensors L and R are swapped",
             "חיישני המגש שמאל וימין הפוכים",
             "The IO list puts <code>PlateSensR</code> on DI&nbsp;21 and "
             "<code>PlateSensL</code> on DI&nbsp;22; <code>PRG_IoMap</code> does "
             "the opposite. Harmless for the cycle while the gate is an OR, but "
             "the <code>L</code>/<code>R</code> lamps on the main screen are "
             "therefore mislabelled. Settle which physical side is which before "
             "changing either end.",
             "רשימת ה-IO ממקמת את <code>PlateSensR</code> ב-DI&nbsp;21 ואת "
             "<code>PlateSensL</code> ב-DI&nbsp;22; <code>PRG_IoMap</code> עושה "
             "את ההפוך. לא מזיק למחזור כל עוד השער הוא OR, אך משמעות הדבר שנוריות "
             "<code>L</code>/<code>R</code> במסך הראשי מסומנות שגוי. קבע איזה צד "
             "פיזי הוא מה לפני שינוי אחד הצדדים."),

        # ---------------------------------------------------------------- 8
        H("8 &middot; Diagnostics", "8 &middot; אבחון", anchor="diagnostics"),
        Steps([
            ("<strong>Log page first.</strong> It shows the 20 newest events "
             "with a timestamp, and the sequence records <em>every</em> state "
             "transition. A fault entry carries the failing step's text.",
             "<strong>קודם כל מסך היומן.</strong> הוא מציג את 20 האירועים "
             "החדשים עם חותמת זמן, והרצף מתעד <em>כל</em> מעבר מצב. רשומת תקלה "
             "מכילה את הטקסט של השלב שנכשל."),
            ("Tick <strong>Debug</strong> on the Log page to add every robot "
             "frame sent and received. Untick it afterwards — the ring is only "
             "20 entries and debug traffic fills it in seconds.",
             "סמן <strong>Debug</strong> במסך היומן כדי להוסיף כל מסגרת רובוט "
             "שנשלחה והתקבלה. בטל את הסימון לאחר מכן — הטבעת מכילה 20 רשומות "
             "בלבד ותעבורת ניפוי ממלאת אותה בשניות."),
            ("<strong>Robot page</strong> for the link: connection state, "
             "packets in and out, the last frame each way, and the two numbers "
             "actually being exchanged.",
             "<strong>מסך הרובוט</strong> לבדיקת הקישור: מצב חיבור, מנות נכנסות "
             "ויוצאות, המסגרת האחרונה בכל כיוון, ושני המספרים שמוחלפים בפועל."),
            ("If the link says <em>Connected</em>, packets are climbing, and yet "
             "no cycle ever starts — check what <em>Last Rx</em> says. A reply "
             "that is not a <code>CMD:</code> frame means the robot software "
             "does not implement the state channel.",
             "אם הקישור מציג <em>Connected</em>, המנות עולות, ובכל זאת אף מחזור "
             "לא מתחיל — בדוק מה מציג <em>Last Rx</em>. תשובה שאינה מסגרת "
             "<code>CMD:</code> פירושה שתוכנת הרובוט אינה מיישמת את ערוץ המצב."),
            ("The timestamps are only as good as the panel clock. If it shows "
             "<code>--:--:--</code> the clock is unset, which is honest rather "
             "than wrong.",
             "חותמות הזמן טובות כמו שעון הפאנל. אם מוצג <code>--:--:--</code> "
             "השעון לא כוון — זה כנה ולא שגוי."),
        ]),
        Note("info", "Bench test scripts",
             "סקריפטים לבדיקה בשולחן",
             "<code>scripts/pb_test/pb_test_procedure.py</code> exercises all "
             "three buttons in every machine state over ADS and writes an HTML "
             "report (57 checks). "
             "<code>scripts/pb_test/cycle_trace.py</code> runs one complete "
             "cycle with the pistons emulated and checks the coil pattern of "
             "every state. <strong>Neither may be pointed at a machine with air "
             "connected.</strong>",
             "<code>scripts/pb_test/pb_test_procedure.py</code> בודק את שלושת "
             "הלחצנים בכל מצבי המכונה דרך ADS וכותב דוח HTML (57 בדיקות). "
             "<code>scripts/pb_test/cycle_trace.py</code> מריץ מחזור שלם עם "
             "בוכנות מדומות ובודק את תבנית הסלילים בכל מצב. <strong>אין להפנות "
             "אף אחד מהם למכונה עם אוויר מחובר.</strong>"),

        # ---------------------------------------------------------------- 9
        H("9 &middot; Log to file (CSV)",
          "9 &middot; Log to file (CSV) <span class=\"ltr\">(English only)</span>",
          anchor="filelog"),
        Note("info", "This section is in English only",
             "\u05d4\u05e4\u05e8\u05e7 \u05d4\u05d6\u05d4 \u05d1\u05d0\u05e0\u05d2\u05dc\u05d9\u05ea \u05d1\u05dc\u05d1\u05d3",
             "The rest of section 9 has not been translated yet.",
             ltr("The rest of section 9 has not been translated yet.")),
        P("The Log page keeps only the 20 newest events and loses everything on "
          "power-down. The panel can also write the log to its own Compact Flash, "
          "so a fault overnight with no laptop attached still leaves a record you "
          "can read the next morning. It is <strong>off by default</strong> "
          "because writing to the card costs flash life.",
          ltr("The Log page keeps only the 20 newest events and loses everything "
              "on power-down. The panel can also write the log to its own Compact "
              "Flash, so a fault overnight with no laptop attached still leaves a "
              "record you can read the next morning. It is <strong>off by "
              "default</strong> because writing to the card costs flash life.")),
        Steps([
            ("<strong>Turn it on.</strong> Tick <strong>File log</strong> on the "
             "Log page. That is the only control on the panel, and the setting "
             "survives a power cycle.",
             ltr("<strong>Turn it on.</strong> Tick <strong>File log</strong> on "
                 "the Log page. That is the only control on the panel, and the "
                 "setting survives a power cycle.")),
            ("<strong>The panel writes</strong> "
             "<code>\\Hard Disk\\Logs\\flower-YYYY-MM-DD.csv</code>. There is no "
             "file viewer on the panel, so the file is for copying off, not for "
             "reading here.",
             ltr("<strong>The panel writes</strong> "
                 "<code>\\Hard Disk\\Logs\\flower-YYYY-MM-DD.csv</code>. There is "
                 "no file viewer on the panel, so the file is for copying off, "
                 "not for reading here.")),
            ("<strong>Fetch it over FTP.</strong> Type "
             "<code>ftp://&lt;panel-ip&gt;/Logs/</code> into Windows Explorer "
             "&mdash; for example <code>ftp://192.168.1.100/Logs/</code>. No user "
             "name or password. Drag the file off and open it in Excel.",
             ltr("<strong>Fetch it over FTP.</strong> Type "
                 "<code>ftp://&lt;panel-ip&gt;/Logs/</code> into Windows Explorer "
                 "&mdash; for example <code>ftp://192.168.1.100/Logs/</code>. No "
                 "user name or password. Drag the file off and open it in "
                 "Excel.")),
            ("<strong>Untick it when you are done</strong> unless the machine is "
             "meant to keep logging.",
             ltr("<strong>Untick it when you are done</strong> unless the machine "
                 "is meant to keep logging.")),
        ]),
        Note("warn", "The panel can switch it on but cannot show you whether it is working",
             "\u05d1\u05d0\u05e0\u05d2\u05dc\u05d9\u05ea",
             "The checkbox is the only file-log control on the panel. The status "
             "fields &mdash; current file, bytes written, files on disk, and any "
             "error &mdash; are only on FlowerPyHmi or over ADS. What the panel "
             "<em>does</em> show is a failure: a write error puts one "
             "<strong>ERR</strong> line in the Log list, so if logging has stopped "
             "working you will see it there.",
             ltr("The checkbox is the only file-log control on the panel. The "
                 "status fields &mdash; current file, bytes written, files on disk, "
                 "and any error &mdash; are only on FlowerPyHmi or over ADS. What "
                 "the panel <em>does</em> show is a failure: a write error puts one "
                 "<strong>ERR</strong> line in the Log list, so if logging has "
                 "stopped working you will see it there.")),
        Table([("Column", "Column"), ("Holds", "Holds")],
              [[("<code>time</code>", "<code>time</code>"),
                ("Panel clock, <code>HH:MM:SS</code>. Reads "
                 "<code>--:--:--</code> if the panel clock is not set.",
                 "Panel clock, <code>HH:MM:SS</code>. Reads "
                 "<code>--:--:--</code> if the panel clock is not set.")],
               [("<code>severity</code>", "<code>severity</code>"),
                ("<code>INFO</code>, <code>WARN</code> or <code>ERR</code>. "
                 "<code>DBG</code> is never written to the file, even with Debug "
                 "ticked &mdash; the 1 Hz robot trace would bury it.",
                 "<code>INFO</code>, <code>WARN</code> or <code>ERR</code>. "
                 "<code>DBG</code> is never written to the file, even with Debug "
                 "ticked &mdash; the 1 Hz robot trace would bury it.")],
               [("<code>source</code>", "<code>source</code>"),
                ("Which part reported it, e.g. <code>Robot</code>, "
                 "<code>Persist</code>, <code>LogCsv</code>.",
                 "Which part reported it, e.g. <code>Robot</code>, "
                 "<code>Persist</code>, <code>LogCsv</code>.")],
               [("<code>message</code>", "<code>message</code>"),
                ("The same text the Log page shows.",
                 "The same text the Log page shows.")]]),
        Note("info", "One file a day, and old ones are deleted for you",
             "\u05d1\u05d0\u05e0\u05d2\u05dc\u05d9\u05ea",
             "A new file starts each day. If one day gets busy the file rolls at "
             "512 KB into <code>flower-YYYY-MM-DD_002.csv</code>, "
             "<code>_003</code> and so on. Once the folder passes 16 MB the "
             "oldest files are deleted automatically, so it cannot fill the card. "
             "Those three limits are adjustable, but only from FlowerPyHmi.",
             ltr("A new file starts each day. If one day gets busy the file rolls "
                 "at 512 KB into <code>flower-YYYY-MM-DD_002.csv</code>, "
                 "<code>_003</code> and so on. Once the folder passes 16 MB the "
                 "oldest files are deleted automatically, so it cannot fill the "
                 "card. Those three limits are adjustable, but only from "
                 "FlowerPyHmi.")),
        Note("warn", "A row saying &ldquo;entries lost&rdquo; is real, and is telling you the truth",
             "\u05d1\u05d0\u05e0\u05d2\u05dc\u05d9\u05ea",
             "Under a heavy burst the machine can produce log entries faster than "
             "they reach the card, and the oldest are overwritten before they are "
             "written out. When that happens the file itself gets a line like "
             "<code>312 entries lost - CSV writer fell behind the ring</code> at "
             "the point where the gap is. Treat it as a genuine hole in the record, "
             "not as a fault in the logger.",
             ltr("Under a heavy burst the machine can produce log entries faster "
                 "than they reach the card, and the oldest are overwritten before "
                 "they are written out. When that happens the file itself gets a "
                 "line like <code>312 entries lost - CSV writer fell behind the "
                 "ring</code> at the point where the gap is. Treat it as a genuine "
                 "hole in the record, not as a fault in the logger.")),
        Note("danger", "Never point the log folder outside <code>\\Hard Disk\\</code>",
             "\u05d1\u05d0\u05e0\u05d2\u05dc\u05d9\u05ea",
             "The folder is set by <code>sDir</code> and must stay under "
             "<code>\\Hard Disk\\</code>, which is the Compact Flash. "
             "<code>\\Temp\\</code> and the drive root <code>\\</code> also accept "
             "files, but they live in RAM and are <strong>emptied on every "
             "restart</strong> &mdash; so logging would appear to work perfectly "
             "and then lose everything on the one event you wanted it for.",
             ltr("The folder is set by <code>sDir</code> and must stay under "
                 "<code>\\Hard Disk\\</code>, which is the Compact Flash. "
                 "<code>\\Temp\\</code> and the drive root <code>\\</code> also "
                 "accept files, but they live in RAM and are <strong>emptied on "
                 "every restart</strong> &mdash; so logging would appear to work "
                 "perfectly and then lose everything on the one event you wanted "
                 "it for.")),
        H("10 &middot; Commissioning notes",
          "10 &middot; הערות הרצה ראשונית", anchor="commissioning"),
        UL([("<strong>The robot IP is persistent.</strong> Changing the default "
             "in the source does <em>not</em> retarget a panel that has already "
             "run — the stored value wins. Use the Robot screen.",
             "<strong>כתובת ה-IP של הרובוט נשמרת.</strong> שינוי ברירת המחדל "
             "בקוד <em>אינו</em> מפנה מחדש פאנל שכבר רץ — הערך השמור קובע. "
             "השתמש במסך הרובוט."),
            ("<strong>Turn off both bench flags</strong> "
             "(<code>bNoSensors</code>, <code>bBypassPlateSensors</code>) before "
             "production. They persist.",
             "<strong>כבה את שני דגלי השולחן</strong> "
             "(<code>bNoSensors</code>, <code>bBypassPlateSensors</code>) לפני "
             "ייצור. הם נשמרים."),
            ("<strong>Never merge the bench target configuration.</strong> The "
             "local development setup disables the fieldbus; shipping it would "
             "give the machine a build with no IO.",
             "<strong>לעולם אל תמזג את תצורת יעד השולחן.</strong> סביבת הפיתוח "
             "המקומית מנטרלת את אפיק השדה; שליחתה תיתן למכונה גרסה בלי IO."),
            ("<strong>A full cycle on real sensors has never been run.</strong> "
             "Every test so far used emulated or bypassed sensors. Expect the "
             "first real cycle to reveal timing that needs tuning.",
             "<strong>מחזור שלם על חיישנים אמיתיים מעולם לא הורץ.</strong> כל "
             "הבדיקות עד כה השתמשו בחיישנים מדומים או מבוטלים. צפה שהמחזור "
             "האמיתי הראשון יחשוף תזמונים שדורשים כיול.")]),
    ]


def build():
    return page(
        "technician-manual.html",
        "Technician's manual", "מדריך לטכנאי",
        "The detailed reference: sequence, error codes, settings, IO, robot "
        "protocol, diagnostics and the deviations you need to know about. For "
        'day-to-day running see the <a href="operator-manual.html">operator '
        "manual</a>.",
        "המדריך המפורט: רצף, קודי תקלה, הגדרות, IO, פרוטוקול רובוט, אבחון "
        'והחריגות שחשוב להכיר. להפעלה יומיומית ראה את <a href="operator-manual.html">'
        "מדריך המפעיל</a>.",
        blocks())
