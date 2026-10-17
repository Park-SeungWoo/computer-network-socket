from datetime import datetime

from core.utils.styler import ANSIStyler


def log(txt: str, color: str):
    print(ANSIStyler.style(f"[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {txt}", color))