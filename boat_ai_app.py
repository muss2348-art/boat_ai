# boat_ai_app.py
# BOATRACE AI v8.2
# 3連単オッズ本文マトリクス解析追加版
# GitHub + Streamlit Cloud 用

import re
import itertools
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Tuple

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


APP_VERSION = "v8.2 3連単オッズ本文マトリクス解析追加版"

JCD_MAP = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川", "06": "浜名湖",
    "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島", "17": "宮島", "18": "徳山",
    "19": "下関", "20": "若松", "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


@dataclass
class Racer:
    lane: int
    name: str
    klass: str = "B1"
    avg_st: float = 0.18
    national_win: float = 0.0
    national_2: float = 0.0
    national_3: float = 0.0
    local_win: float = 0.0
    local_2: float = 0.0
    local_3: float = 0.0
    motor_no: int = 0
    motor_2: float = 0.0
    motor_3: float = 0.0
    boat_no: int = 0
    boat_2: float = 0.0
    boat_3: float = 0.0
    display_time: float = 0.0
    tilt: float = 0.0
    tenji_st: float = 0.0
    tenji_f: bool = False
    score: float = 0.0
    data_status: str = ""


def zen_to_han(s: str) -> str:
    if s is None:
        return ""
    return str(s).translate(str.maketrans(
        "０１２３４５６７８９．－＋　",
        "0123456789.-+ "
    ))


def clean_text(s: str) -> str:
    s = zen_to_han(str(s))
    s = s.replace("\xa0", " ")
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n+", "\n", s)
    return s.strip()


def safe_float(x, default=0.0) -> float:
    try:
        x = clean_text(x).replace("%", "").replace("F", "").strip()
        if x in ["", "-", "－", "None", "nan", "欠場", "不成立"]:
            return default
        return float(x)
    except Exception:
        return default


def safe_int(x, default=0) -> int:
    try:
        x = clean_text(x)
        if x in ["", "-", "－", "None", "nan"]:
            return default
        return int(float(x))
    except Exception:
        return default


def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def parse_query_from_url(url: str) -> Tuple[str, str, str]:
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    rno = q.get("rno", [""])[0]
    jcd = q.get("jcd", [""])[0].zfill(2)
    hd = q.get("hd", [""])[0]
    if not rno or not jcd or not hd:
        raise ValueError("URLから rno / jcd / hd を取得できませんでした。")
    return rno, jcd, hd


def make_url(page: str, rno: str, jcd: str, hd: str) -> str:
    return f"https://www.boatrace.jp/owpc/pc/race/{page}?rno={rno}&jcd={jcd}&hd={hd}"


def soup_lines(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    return [clean_text(x) for x in text.splitlines() if clean_text(x)]


def extract_event_name(html: str, place: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text(soup.title.get_text(" ")) if soup.title else ""

    if title:
        title = re.sub(r"出走表.*", "", title)
        title = re.sub(r"【.*", "", title)
        title = title.replace("BOAT RACE", "")
        title = title.replace("ボートレース", "")
        title = title.replace(place, "")
        title = title.strip(" -｜|")
        if 5 <= len(title) <= 80 and title not in ["G3", "ヴィーナスシリーズ", "ルーキーシリーズ"]:
            return title

    ng = ["G1", "G2", "G3", "SG", "ヴィーナスシリーズ", "ルーキーシリーズ", "一般戦", "出走表"]
    for tag in soup.find_all(["h1", "h2", "h3", "div", "p", "span"]):
        txt = clean_text(tag.get_text(" "))
        if txt and txt not in ng:
            if any(k in txt for k in ["杯", "選手権", "グランプリ", "ダービー", "周年", "マンスリー"]):
                if 5 <= len(txt) <= 80:
                    return txt
    return ""


def cell_texts(row) -> List[str]:
    return [clean_text(td.get_text("\n")) for td in row.find_all(["td", "th"])]


def extract_lane_from_text(text: str) -> int:
    m = re.match(r"^([1-6])(?:\s|$|Image)", clean_text(text))
    return int(m.group(1)) if m else 0


def extract_name_from_text(text: str) -> str:
    lines = [clean_text(x) for x in text.splitlines() if clean_text(x)]

    for i, line in enumerate(lines):
        if re.search(r"\d{4}\s*/\s*[AB][12]", line):
            for cand in lines[i + 1:i + 8]:
                if (
                    cand
                    and not re.search(r"\d|kg|F\d|L\d|/", cand)
                    and "支部" not in cand
                    and "出身" not in cand
                    and "年齢" not in cand
                    and "全国" not in cand
                    and "当地" not in cand
                    and "モーター" not in cand
                    and "ボート" not in cand
                ):
                    return cand.replace(" ", "")

    for line in lines:
        if re.fullmatch(r"[一-龥ぁ-んァ-ヶー]+\s*[一-龥ぁ-んァ-ヶー]+", line):
            return line.replace(" ", "")

    return ""


def extract_reg_class(text: str) -> Tuple[str, str]:
    m = re.search(r"(\d{4})\s*/\s*([AB][12])", text)
    return (m.group(1), m.group(2)) if m else ("", "B1")


def parse_stats_from_racer_text(text: str) -> Dict[str, float]:
    nums = [safe_float(x) for x in re.findall(r"[-+]?\d+\.\d+", clean_text(text))]

    avg_st = 0.18
    start_idx = None
    for i, n in enumerate(nums):
        if 0.08 <= n <= 0.35:
            avg_st = n
            start_idx = i
            break

    rate = nums[start_idx + 1:] if start_idx is not None else nums

    def get(i, default=0.0):
        return rate[i] if len(rate) > i else default

    return {
        "avg_st": avg_st,
        "national_win": get(0),
        "national_2": get(1),
        "national_3": get(2),
        "local_win": get(3),
        "local_2": get(4),
        "local_3": get(5),
        "motor_2": get(6),
        "motor_3": get(7),
        "boat_2": get(8),
        "boat_3": get(9),
    }


def extract_motor_boat_no(text: str) -> Tuple[int, int]:
    text = clean_text(text)
    motor_no = 0
    boat_no = 0

    m_motor = re.search(r"モーター\s*([0-9]{1,3})", text)
    if m_motor:
        motor_no = safe_int(m_motor.group(1))

    m_boat = re.search(r"ボート\s*([0-9]{1,3})", text)
    if m_boat:
        boat_no = safe_int(m_boat.group(1))

    if not motor_no or not boat_no:
        int_nums = [safe_int(x) for x in re.findall(r"\b\d{1,3}\b", text)]
        cands = [x for x in int_nums if 1 <= x <= 99]
        if len(cands) >= 2:
            motor_no = motor_no or cands[-2]
            boat_no = boat_no or cands[-1]

    return motor_no, boat_no


def parse_racer_from_text(lane: int, text: str) -> Racer:
    _, klass = extract_reg_class(text)
    name = extract_name_from_text(text) or f"{lane}号艇"
    stats = parse_stats_from_racer_text(text)
    motor_no, boat_no = extract_motor_boat_no(text)

    status = [
        "名前OK" if name != f"{lane}号艇" else "名前取得弱い",
        "全国OK" if stats["national_2"] > 0 else "全国2連弱い",
        "当地OK" if stats["local_2"] > 0 else "当地2連弱い",
        "機力OK" if stats["motor_2"] > 0 else "モーター弱い",
    ]

    return Racer(
        lane=lane,
        name=name,
        klass=klass,
        avg_st=stats["avg_st"],
        national_win=stats["national_win"],
        national_2=stats["national_2"],
        national_3=stats["national_3"],
        local_win=stats["local_win"],
        local_2=stats["local_2"],
        local_3=stats["local_3"],
        motor_no=motor_no,
        motor_2=stats["motor_2"],
        motor_3=stats["motor_3"],
        boat_no=boat_no,
        boat_2=stats["boat_2"],
        boat_3=stats["boat_3"],
        data_status=" / ".join(status),
    )


def parse_racelist_by_tables(html: str) -> List[Racer]:
    soup = BeautifulSoup(html, "html.parser")
    racers = []

    for row in soup.find_all("tr"):
        vals = cell_texts(row)
        if not vals:
            continue

        row_text = "\n".join(vals)
        if not re.search(r"\d{4}\s*/\s*[AB][12]", row_text):
            continue

        lane = 0
        for v in vals[:4]:
            lane = extract_lane_from_text(v)
            if lane:
                break

        if not lane:
            lane = extract_lane_from_text(row_text)

        if lane:
            racers.append(parse_racer_from_text(lane, row_text))

    uniq = {}
    for r in racers:
        if r.lane not in uniq:
            uniq[r.lane] = r

    return [uniq[k] for k in sorted(uniq)]


def parse_racelist_by_lines(html: str) -> List[Racer]:
    lines = soup_lines(html)
    starts = []

    for i, line in enumerate(lines):
        lane = extract_lane_from_text(line)
        if not lane:
            continue
        look = "\n".join(lines[i:i + 30])
        if re.search(r"\d{4}\s*/\s*[AB][12]", look):
            starts.append((i, lane))

    uniq_starts = []
    seen = set()
    for i, lane in starts:
        if lane not in seen:
            uniq_starts.append((i, lane))
            seen.add(lane)

    racers = []
    for idx, (start_i, lane) in enumerate(uniq_starts):
        end_i = uniq_starts[idx + 1][0] if idx + 1 < len(uniq_starts) else len(lines)
        racers.append(parse_racer_from_text(lane, "\n".join(lines[start_i:end_i])))

    return sorted(racers, key=lambda r: r.lane)


def parse_racelist(html: str, place: str) -> Tuple[List[Racer], Dict]:
    event_name = extract_event_name(html, place)
    racers = parse_racelist_by_tables(html)
    method = "table"

    if len(racers) < 6:
        line_racers = parse_racelist_by_lines(html)
        if len(line_racers) > len(racers):
            racers = line_racers
            method = "lines"

    uniq = {r.lane: r for r in racers}
    for lane in range(1, 7):
        if lane not in uniq:
            uniq[lane] = Racer(lane=lane, name=f"{lane}号艇", data_status="出走表フォールバック")

    return [uniq[k] for k in sorted(uniq)], {
        "event_name": event_name,
        "method": method,
        "raw_lines_sample": soup_lines(html)[:220],
    }


def parse_beforeinfo(html: str, racers: List[Racer]) -> Dict:
    soup = BeautifulSoup(html, "html.parser")
    by_lane = {r.lane: r for r in racers}

    for row in soup.find_all("tr"):
        vals = cell_texts(row)
        if not vals:
            continue

        row_text = "\n".join(vals)
        lane = 0
        for v in vals[:4]:
            lane = extract_lane_from_text(v)
            if lane:
                break

        if not lane or lane not in by_lane:
            continue

        floats = [safe_float(x) for x in re.findall(r"[-+]?\d+\.\d+", row_text)]

        display_candidates = [x for x in floats if 6.20 <= x <= 7.80]
        if display_candidates:
            by_lane[lane].display_time = display_candidates[0]

        tilt_candidates = [x for x in floats if -0.5 <= x <= 3.0]
        for t in tilt_candidates:
            if t != by_lane[lane].display_time:
                by_lane[lane].tilt = t
                break

    joined = "\n".join(soup_lines(html))
    for m in re.finditer(r"([1-6])\s+(F)?\.?(\d{2})", joined):
        lane = int(m.group(1))
        if lane in by_lane:
            st = safe_float("0." + m.group(3))
            if 0.00 <= st <= 0.40:
                by_lane[lane].tenji_st = st
                by_lane[lane].tenji_f = bool(m.group(2))

    return {"beforeinfo_ok": True}


def normalize_combo_key(s: str) -> str:
    s = clean_text(s)
    s = s.replace("→", "-").replace("ー", "-").replace("－", "-")
    s = re.sub(r"\s+", "", s)

    m = re.search(r"([1-6])[-]?([1-6])[-]?([1-6])", s)
    if not m:
        return ""

    a, b, c = m.groups()
    if len({a, b, c}) != 3:
        return ""

    return f"{a}-{b}-{c}"


def parse_odds_from_plain_text(text: str) -> Dict[str, float]:
    odds: Dict[str, float] = {}
    text = clean_text(text)

    for m in re.finditer(r"([1-6])[-ー－]([1-6])[-ー－]([1-6])\s+(\d+\.\d+)", text):
        a, b, c, v = m.groups()
        if len({a, b, c}) == 3:
            odds[f"{a}-{b}-{c}"] = safe_float(v)

    for m in re.finditer(r"\b([1-6]{3})\s+(\d+\.\d+)\b", text):
        nums, v = m.groups()
        a, b, c = nums[0], nums[1], nums[2]
        if len({a, b, c}) == 3:
            odds[f"{a}-{b}-{c}"] = safe_float(v)

    for m in re.finditer(r"([1-6])\s*→\s*([1-6])\s*→\s*([1-6])\s+(\d+\.\d+)", text):
        a, b, c, v = m.groups()
        if len({a, b, c}) == 3:
            odds[f"{a}-{b}-{c}"] = safe_float(v)

    return odds


def parse_script_embedded_odds(html: str) -> Dict[str, float]:
    odds: Dict[str, float] = {}

    for m in re.finditer(r'["\']?([1-6])[-_]?([1-6])[-_]?([1-6])["\']?\s*[:=]\s*["\']?(\d+\.\d+)["\']?', html):
        a, b, c, v = m.groups()
        if len({a, b, c}) == 3:
            odds[f"{a}-{b}-{c}"] = safe_float(v)

    for m in re.finditer(r'["\']([1-6]{3})["\']\s*[:=]\s*["\']?(\d+\.\d+)["\']?', html):
        nums, v = m.groups()
        a, b, c = nums[0], nums[1], nums[2]
        if len({a, b, c}) == 3:
            odds[f"{a}-{b}-{c}"] = safe_float(v)

    return odds


def parse_odds_from_table_cells(html: str) -> Dict[str, float]:
    odds: Dict[str, float] = {}
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        table_text = clean_text(table.get_text(" "))
        odds.update(parse_odds_from_plain_text(table_text))

        for row in table.find_all("tr"):
            cells = cell_texts(row)
            if not cells:
                continue

            row_text = " ".join(cells)
            odds.update(parse_odds_from_plain_text(row_text))

            for i in range(len(cells) - 1):
                key = normalize_combo_key(cells[i])
                val = safe_float(cells[i + 1], 0.0)
                if key and val > 0:
                    odds[key] = val

            for i in range(len(cells) - 3):
                a, b, c, v = cells[i], cells[i + 1], cells[i + 2], cells[i + 3]
                if re.fullmatch(r"[1-6]", a) and re.fullmatch(r"[1-6]", b) and re.fullmatch(r"[1-6]", c):
                    if len({a, b, c}) == 3:
                        val = safe_float(v, 0.0)
                        if val > 0:
                            odds[f"{a}-{b}-{c}"] = val

    try:
        tables = pd.read_html(html)
        for df in tables:
            flat = [clean_text(x) for x in map(str, df.values.flatten()) if clean_text(x)]
            joined = " ".join(flat)
            odds.update(parse_odds_from_plain_text(joined))

            for i in range(len(flat) - 1):
                key = normalize_combo_key(flat[i])
                val = safe_float(flat[i + 1], 0.0)
                if key and val > 0:
                    odds[key] = val
    except Exception:
        pass

    return odds


def parse_boatrace_text_matrix_3t(html: str) -> Dict[str, float]:
    """
    v8.2本命ロジック。
    BOATRACE公式3連単オッズ本文は、
    6艇分が横並びで以下のように並ぶ。

    2 3 72.7 / 1 3 97.6 / 1 2 240.1 / ...
    1行 = 6艇分 × (2着, 3着, オッズ) = 18トークン
    それを20行分読むと 120点。
    """
    odds: Dict[str, float] = {}
    lines = soup_lines(html)

    try:
        start = lines.index("3連単オッズ") + 1
    except ValueError:
        return odds

    end = len(lines)
    for i, line in enumerate(lines[start:], start=start):
        if "締切時オッズは" in line:
            end = i
            break

    block = lines[start:end]

    nums = []
    for x in block:
        if re.fullmatch(r"[1-6]", x):
            nums.append(x)
        elif re.fullmatch(r"\d+\.\d+", x):
            nums.append(x)

    best = []
    for offset in range(0, min(30, len(nums))):
        remain = nums[offset:]
        if len(remain) < 360:
            continue

        sample = remain[:18]
        ok = True
        for j in range(0, 18, 3):
            if not re.fullmatch(r"[1-6]", sample[j]):
                ok = False
            if not re.fullmatch(r"[1-6]", sample[j + 1]):
                ok = False
            if not re.fullmatch(r"\d+\.\d+", sample[j + 2]):
                ok = False

        if ok:
            best = remain
            break

    if not best:
        return odds

    firsts = [1, 2, 3, 4, 5, 6]
    rows = [best[i:i + 18] for i in range(0, min(len(best), 360), 18)]

    for row in rows:
        if len(row) < 18:
            continue

        for col, first in enumerate(firsts):
            i = col * 3
            second = row[i]
            third = row[i + 1]
            val = safe_float(row[i + 2], 0.0)

            if re.fullmatch(r"[1-6]", second) and re.fullmatch(r"[1-6]", third) and val > 0:
                a = str(first)
                b = second
                c = third
                if len({a, b, c}) == 3:
                    odds[f"{a}-{b}-{c}"] = val

    return odds


def fetch_and_parse_odds3t(rno: str, jcd: str, hd: str) -> Tuple[Dict[str, float], Dict]:
    urls = [
        make_url("odds3t", rno, jcd, hd),
        f"https://www.boatrace.jp/owpc/pc/race/odds3t?hd={hd}&jcd={jcd}&rno={rno}",
        f"https://www.boatrace.jp/owpc/pc/race/odds3t?rno={rno}&jcd={jcd}&hd={hd}",
        f"https://www.boatrace.jp/owpc/pc/race/odds3t?rno={rno}&jcd={jcd}&hd={hd}&type=3",
    ]

    best_odds: Dict[str, float] = {}
    best_url = urls[0]
    errors = []
    html_sample = ""

    for url in urls:
        try:
            html = fetch_html(url)
            html_sample = clean_text(BeautifulSoup(html, "html.parser").get_text("\n"))[:3000]

            odds = {}
            odds.update(parse_script_embedded_odds(html))
            odds.update(parse_odds_from_plain_text(BeautifulSoup(html, "html.parser").get_text(" ")))
            odds.update(parse_odds_from_table_cells(html))
            odds.update(parse_boatrace_text_matrix_3t(html))

            if len(odds) > len(best_odds):
                best_odds = odds
                best_url = url
        except Exception as e:
            errors.append(f"{url}: {e}")

    meta = {
        "odds_url": best_url,
        "odds_count": len(best_odds),
        "odds_errors": errors,
        "odds_sample": dict(list(best_odds.items())[:80]),
        "odds_text_sample": html_sample,
    }
    return best_odds, meta


def class_bonus(klass: str) -> float:
    return {"A1": 8.0, "A2": 4.5, "B1": 0.0, "B2": -3.0}.get(klass, 0.0)


def calculate_scores(racers: List[Racer]) -> List[Racer]:
    for r in racers:
        score = 50.0
        score += class_bonus(r.klass)
        score += r.national_2 * 0.34
        score += r.national_3 * 0.10
        score += r.local_2 * 0.16
        score += r.motor_2 * 0.22
        score += r.boat_2 * 0.08

        if r.avg_st:
            score += max(0, (0.20 - r.avg_st) * 80)
        if r.display_time:
            score += max(0, (7.25 - r.display_time) * 20)
        if r.tenji_st:
            score += max(0, (0.15 - r.tenji_st) * 55)
        if r.tenji_f:
            score -= 7.0

        score += {1: 9.5, 2: 4.5, 3: 2.5, 4: 1.0, 5: -2.0, 6: -4.0}.get(r.lane, 0.0)
        r.score = round(score, 1)

    return sorted(racers, key=lambda x: x.score, reverse=True)


def make_ai_table(racers: List[Racer]) -> pd.DataFrame:
    ranked = calculate_scores(racers)

    rows = []
    for i, r in enumerate(ranked, start=1):
        rows.append({
            "順位": i,
            "艇": r.lane,
            "選手": r.name,
            "級別": r.klass,
            "AI指数": r.score,
            "展示": r.display_time,
            "展示ST": f"{'F' if r.tenji_f else ''}{r.tenji_st:.2f}" if r.tenji_st else 0,
            "平均ST": r.avg_st,
            "全国勝率": r.national_win,
            "全国2連率": r.national_2,
            "全国3連率": r.national_3,
            "当地勝率": r.local_win,
            "当地2連率": r.local_2,
            "当地3連率": r.local_3,
            "モーター2連率": r.motor_2,
            "モーター3連率": r.motor_3,
            "ボート2連率": r.boat_2,
            "ボート3連率": r.boat_3,
            "データ状態": r.data_status,
        })

    return pd.DataFrame(rows)


def combo_score(combo: Tuple[int, int, int], racer_map: Dict[int, Racer]) -> float:
    a, b, c = combo
    r1, r2, r3 = racer_map[a], racer_map[b], racer_map[c]

    s = r1.score * 1.00 + r2.score * 0.68 + r3.score * 0.46

    if a == 1:
        s += 7.0
    if r1.klass == "A1":
        s += 5.0
    elif r1.klass == "A2":
        s += 2.0

    for x in [r2, r3]:
        if x.display_time and x.display_time <= 7.12:
            s += 2.0
        if x.tenji_st and x.tenji_st <= 0.08:
            s += 1.5

    if a == 6 and r1.score < 95:
        s -= 8.0

    return round(s, 2)


def generate_predictions(racers: List[Racer], odds: Dict[str, float]) -> pd.DataFrame:
    ranked = calculate_scores(racers)
    racer_map = {r.lane: r for r in racers}

    rows = []
    for combo in itertools.permutations([1, 2, 3, 4, 5, 6], 3):
        key = f"{combo[0]}-{combo[1]}-{combo[2]}"
        odd = odds.get(key, 0.0)
        value = combo_score(combo, racer_map)

        if odd > 0:
            if 7.0 <= odd <= 35.0:
                value += 8.0
            elif 35.0 < odd <= 90.0:
                value += 4.0
            elif odd < 5.0:
                value -= 5.0
            elif odd > 150:
                value -= 3.0

        rows.append({
            "買い目": key,
            "評価": round(value, 2),
            "オッズ": odd,
        })

    df = pd.DataFrame(rows).sort_values("評価", ascending=False).reset_index(drop=True)

    labels = []
    for i, row in df.iterrows():
        odd = row["オッズ"]
        if i < 2:
            labels.append("熱🔥")
        elif i < 6:
            labels.append("本線")
        elif (odd and odd >= 35) or (not odd and i < 10):
            labels.append("穴")
        else:
            labels.append("抑え")

    df["区分"] = labels

    top_gap = ranked[0].score - ranked[1].score if len(ranked) >= 2 else 0
    confidence = min(100, max(0, 45 + top_gap * 2.2 + (ranked[0].score - 85) * 0.7))
    confidence = round(confidence, 1)

    df["勝負度"] = confidence
    df["厚張りAI"] = ""

    if confidence >= 72:
        df.loc[df.index[:2], "厚張りAI"] = "候補"
    if confidence >= 82:
        df.loc[df.index[:1], "厚張りAI"] = "強"

    return df.head(14)


def build_note_text(event_name: str, place: str, rno: str, ai_df: pd.DataFrame, pred_df: pd.DataFrame) -> str:
    lines = []
    title = f"{place}{rno}R"
    if event_name:
        title += f"｜{event_name}"

    lines.append(title)
    lines.append("")
    lines.append("【指数表・印】")

    marks = ["◎", "○", "▲", "△", "☆", "消"]
    for i, row in ai_df.iterrows():
        mark = marks[i] if i < len(marks) else ""
        lines.append(f"{mark} {int(row['艇'])}号艇 {row['選手']}｜指数 {row['AI指数']}")

    lines.append("")
    lines.append("【買い目】")
    for _, row in pred_df.head(8).iterrows():
        odds_txt = f"（{row['オッズ']}倍）" if row["オッズ"] else ""
        lines.append(f"{row['区分']} {row['買い目']} {odds_txt}")

    lines.append("")
    lines.append("※指数表・印とは連動していない場合もございます。")
    return "\n".join(lines)


def main():
    st.set_page_config(page_title="BOATRACE AI", page_icon="🚤", layout="wide")

    st.title("🚤 BOATRACE AI")
    st.caption(APP_VERSION)

    default_url = "https://www.boatrace.jp/owpc/pc/race/racelist?rno=2&jcd=20&hd=20260520"
    url = st.text_input("BOATRACE公式 出走表URL", value=default_url)

    col1, col2, col3 = st.columns(3)

    with col1:
        use_before = st.checkbox("直前情報を取得", value=True)
    with col2:
        use_odds = st.checkbox("3連単オッズを取得", value=True)
    with col3:
        debug = st.checkbox("デバッグ表示", value=False)

    if st.button("AI予想を実行", type="primary"):
        try:
            rno, jcd, hd = parse_query_from_url(url)
            place = JCD_MAP.get(jcd, f"jcd={jcd}")

            racelist_url = make_url("racelist", rno, jcd, hd)
            before_url = make_url("beforeinfo", rno, jcd, hd)

            with st.spinner("出走表を取得中..."):
                racelist_html = fetch_html(racelist_url)
                racers, meta = parse_racelist(racelist_html, place)

            if use_before:
                with st.spinner("直前情報を取得中..."):
                    try:
                        before_html = fetch_html(before_url)
                        parse_beforeinfo(before_html, racers)
                    except Exception as e:
                        st.warning(f"直前情報の取得に失敗しました: {e}")

            odds = {}
            odds_meta = {}
            if use_odds:
                with st.spinner("3連単オッズを取得中..."):
                    try:
                        odds, odds_meta = fetch_and_parse_odds3t(rno, jcd, hd)
                    except Exception as e:
                        st.warning(f"オッズ取得に失敗しました: {e}")

            ai_df = make_ai_table(racers)
            pred_df = generate_predictions(racers, odds)

            st.subheader(f"{place} {rno}R")

            if meta.get("event_name"):
                st.write(meta["event_name"])

            name_ok = int((~ai_df["選手"].astype(str).str.contains("号艇")).sum())
            if name_ok == 6:
                st.success("選手名取得：6/6艇 OK")
            else:
                st.warning(f"選手名取得：{name_ok}/6艇。フォールバックが残っています。")

            before_ok = int((ai_df["展示"].astype(float) > 0).sum())
            if use_before:
                if before_ok == 6:
                    st.success("直前情報：展示タイム 6/6艇 OK")
                else:
                    st.warning(f"直前情報：展示タイム {before_ok}/6艇")

            if use_odds:
                if len(odds) >= 100:
                    st.success(f"3連単オッズ：{len(odds)}件取得 OK")
                elif len(odds) > 0:
                    st.warning(f"3連単オッズ：{len(odds)}件取得。まだ一部取得です。")
                else:
                    st.info("3連単オッズ：今回は買い目別オッズを復元できませんでした。指数予想は実行しています。")

            st.markdown("### 指数表")
            st.dataframe(ai_df, width="stretch", hide_index=True)

            st.markdown("### 買い目AI")
            st.dataframe(pred_df, width="stretch", hide_index=True)

            confidence = pred_df["勝負度"].iloc[0] if len(pred_df) else 0
            if confidence >= 82:
                st.error(f"勝負度：{confidence}%　厚張り候補あり")
            elif confidence >= 72:
                st.warning(f"勝負度：{confidence}%　厳選候補")
            else:
                st.info(f"勝負度：{confidence}%　通常評価")

            st.markdown("### Note貼り付け用")
            st.text_area(
                "コピー用",
                value=build_note_text(meta.get("event_name", ""), place, rno, ai_df, pred_df),
                height=260,
            )

            if debug:
                st.markdown("### デバッグURL")
                st.code(
                    f"出走表: {racelist_url}\n"
                    f"直前情報: {before_url}\n"
                    f"3連単オッズ: {odds_meta.get('odds_url', make_url('odds3t', rno, jcd, hd))}"
                )

                st.markdown("### 出走表抽出方式")
                st.write(meta.get("method"))

                st.markdown("### オッズ取得件数")
                st.write(len(odds))

                st.markdown("### オッズサンプル")
                st.write(odds_meta.get("odds_sample", dict(list(odds.items())[:80])))

                st.markdown("### オッズ本文サンプル")
                st.text_area("オッズページ本文", value=odds_meta.get("odds_text_sample", ""), height=250)

                if odds_meta.get("odds_errors"):
                    st.markdown("### オッズ取得エラー")
                    st.write(odds_meta.get("odds_errors"))

        except Exception as e:
            st.error("処理中にエラーが発生しました。")
            st.exception(e)


if __name__ == "__main__":
    main()