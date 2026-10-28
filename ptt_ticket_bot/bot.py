"""PTT KoreaDrama 售票文監控機器人。

掃描 PTT KoreaDrama 版最新幾頁，找出標題含「售票」、且內文提到
指定藝人（預設：金智媛 / KIM JI WON）與指定日期（預設：11/08）的文章，
有新文章就透過 WhatsApp 通知。已通知過的文章記錄在 seen.json，不會重複通知。

WhatsApp 通知方式（擇一，用環境變數設定）：
  1. CallMeBot（免費，個人用最簡單）
       CALLMEBOT_PHONE   例如 +886912345678
       CALLMEBOT_APIKEY  向 CallMeBot 申請到的 apikey
  2. Twilio WhatsApp
       TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
       TWILIO_FROM       例如 whatsapp:+14155238886
       TWILIO_TO         例如 whatsapp:+886912345678

其他可調整的環境變數（逗號分隔）：
  PTT_BOARD          預設 KoreaDrama
  PAGES              每次往回掃幾頁，預設 3
  TITLE_KEYWORDS     標題必須包含其中之一，預設 售票
  ARTIST_KEYWORDS    標題或內文必須包含其中之一，預設 金智媛,KIM JI WON,KIMJIWON,김지원
  DATE_PATTERNS      標題或內文必須符合其中之一的正規表示式，預設比對 11/08、11/8、11.8、1108、11月8日；
                     設成 none 代表不限日期

用法：
  python bot.py              掃描一次
  python bot.py --dry-run    只印出結果，不發通知、不寫 seen.json
  python bot.py --loop 120   每 120 秒掃描一次（在自己電腦上常駐用）
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PTT_BASE = "https://www.ptt.cc"
SEEN_FILE = Path(__file__).with_name("seen.json")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    )
}
COOKIES = {"over18": "1"}

DEFAULT_ARTIST_KEYWORDS = "金智媛,KIM JI WON,KIMJIWON,김지원"
# 11/08、11/8、11.08、11-8、11月8日、1108（前後不能緊接其他數字，避免誤判 111/08、11/080 等）
DEFAULT_DATE_PATTERNS = r"(?<!\d)11\s*[/.\-]\s*0?8(?!\d),(?<!\d)11\s*月\s*0?8\s*日?(?!\d),(?<!\d)1108(?!\d)"


def env_list(name, default):
    raw = os.environ.get(name) or default
    if raw.strip().lower() == "none":
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def normalize(text):
    """去掉空白、轉大寫，讓 'Kim Ji Won'、'KIM JIWON' 都能比對到 'KIMJIWON'。"""
    return re.sub(r"\s+", "", text).upper()


class Matcher:
    def __init__(self, title_keywords, artist_keywords, date_patterns):
        self.title_keywords = title_keywords
        self.artist_keywords = [normalize(k) for k in artist_keywords]
        self.date_patterns = [re.compile(p) for p in date_patterns]

    def title_ok(self, title):
        return any(k in title for k in self.title_keywords)

    def content_ok(self, text):
        norm = normalize(text)
        if not any(k in norm for k in self.artist_keywords):
            return False
        if self.date_patterns and not any(p.search(text) for p in self.date_patterns):
            return False
        return True


def fetch(session, url):
    resp = session.get(url, headers=HEADERS, cookies=COOKIES, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_index(html, page_url):
    """回傳 (文章清單, 上一頁網址)。文章為 dict(id, title, author, url)。"""
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for ent in soup.select("div.r-ent"):
        a = ent.select_one("div.title a")
        if not a:  # 已刪除的文章沒有連結
            continue
        url = urljoin(page_url, a["href"])
        author = ent.select_one("div.author")
        posts.append({
            "id": url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".html"),
            "title": a.get_text(strip=True),
            "author": author.get_text(strip=True) if author else "",
            "url": url,
        })
    prev_url = None
    for btn in soup.select("div.btn-group-paging a.btn"):
        if "上頁" in btn.get_text() and btn.get("href"):
            prev_url = urljoin(page_url, btn["href"])
    return posts, prev_url


def parse_article(html):
    """取出文章正文，去掉推文、文章資訊列與 ※ 開頭的系統行（避免推文時間 11/08 造成誤判）。"""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("#main-content")
    if main is None:
        return ""
    for tag in main.select("div.push, div.article-metaline, div.article-metaline-right"):
        tag.decompose()
    lines = [
        line for line in main.get_text("\n").splitlines()
        if not line.strip().startswith(("※", "◆", "--"))
    ]
    return "\n".join(lines).strip()


def scan(session, board, pages, matcher, seen):
    """回傳符合條件且尚未通知過的文章（由舊到新）。"""
    url = f"{PTT_BASE}/bbs/{board}/index.html"
    candidates = []
    for _ in range(pages):
        posts, prev_url = parse_index(fetch(session, url), url)
        candidates.extend(posts)
        if not prev_url:
            break
        url = prev_url

    hits, checked = [], set()
    for post in candidates:
        if post["id"] in seen or post["id"] in checked or not matcher.title_ok(post["title"]):
            continue
        checked.add(post["id"])
        try:
            body = parse_article(fetch(session, post["url"]))
        except requests.RequestException as e:
            print(f"讀取文章失敗，下次再試：{post['url']} ({e})", file=sys.stderr)
            continue
        if matcher.content_ok(post["title"] + "\n" + body):
            post["summary"] = re.sub(r"\n\s*\n+", "\n", body)[:300]
            hits.append(post)
    hits.sort(key=lambda p: p["id"])  # 文章 ID 含時間戳記，排序即為發文順序
    return hits


def format_message(post):
    return (
        "🎫 PTT 有新的售票文！\n"
        f"{post['title']}\n"
        f"作者：{post['author']}\n"
        f"{post['url']}\n\n"
        f"{post.get('summary', '')}"
    )


def send_whatsapp(session, text):
    if os.environ.get("CALLMEBOT_APIKEY"):
        resp = session.get(
            "https://api.callmebot.com/whatsapp.php",
            params={
                "phone": os.environ["CALLMEBOT_PHONE"],
                "text": text,
                "apikey": os.environ["CALLMEBOT_APIKEY"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        if "ERROR" in resp.text.upper():
            raise RuntimeError(f"CallMeBot 回傳錯誤：{resp.text[:200]}")
    elif os.environ.get("TWILIO_ACCOUNT_SID"):
        sid = os.environ["TWILIO_ACCOUNT_SID"]
        resp = session.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
            data={
                "From": os.environ["TWILIO_FROM"],
                "To": os.environ["TWILIO_TO"],
                "Body": text,
            },
            timeout=30,
        )
        resp.raise_for_status()
    else:
        raise RuntimeError("沒有設定 WhatsApp 通知（CALLMEBOT_* 或 TWILIO_*）")


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run_once(args, matcher):
    session = requests.Session()
    seen = load_seen()
    hits = scan(session, args.board, args.pages, matcher, seen)
    print(f"掃描 {args.board} 最新 {args.pages} 頁，新符合文章 {len(hits)} 篇")
    failed = 0
    for post in hits:
        msg = format_message(post)
        print("-" * 40 + "\n" + msg)
        if args.dry_run:
            continue
        try:
            send_whatsapp(session, msg)
        except Exception as e:  # 通知失敗就不記錄，下次會重送
            failed += 1
            print(f"WhatsApp 通知失敗：{e}", file=sys.stderr)
            continue
        seen.add(post["id"])
        save_seen(seen)
        time.sleep(3)  # CallMeBot 有頻率限制，連續發送間隔一下
    return failed


def main():
    parser = argparse.ArgumentParser(description="PTT 售票文 WhatsApp 通知機器人")
    parser.add_argument("--board", default=os.environ.get("PTT_BOARD") or "KoreaDrama")
    parser.add_argument("--pages", type=int, default=int(os.environ.get("PAGES") or 3))
    parser.add_argument("--dry-run", action="store_true", help="只印出結果，不發通知")
    parser.add_argument("--loop", type=int, metavar="秒", help="每隔幾秒重複掃描")
    args = parser.parse_args()

    matcher = Matcher(
        env_list("TITLE_KEYWORDS", "售票"),
        env_list("ARTIST_KEYWORDS", DEFAULT_ARTIST_KEYWORDS),
        env_list("DATE_PATTERNS", DEFAULT_DATE_PATTERNS),
    )

    if not args.loop:
        sys.exit(1 if run_once(args, matcher) else 0)
    while True:
        try:
            run_once(args, matcher)
        except Exception as e:
            print(f"本輪掃描失敗：{e}", file=sys.stderr)
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
