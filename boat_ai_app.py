# boat_ai_app.py
# BOATRACE AI v10.7
# 見送り強化AI・軽量モード・頭期待値AI・紐抜け対策AI
# GitHub + Streamlit Cloud 用

import re
import itertools
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple

import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup


APP_VERSION = "v10.10 買い目バランス調整版"

JST = timezone(timedelta(hours=9))

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
    motor_2: float = 0.0
    motor_3: float = 0.0
    boat_2: float = 0.0
    boat_3: float = 0.0
    display_time: float = 0.0
    tilt: float = 0.0
    tenji_st: float = 0.0
    tenji_f: bool = False
    score: float = 0.0
    head_power: float = 0.0
    place_power: float = 0.0
    third_power: float = 0.0
    data_status: str = ""


def zen_to_han(s: str) -> str:
    if s is None:
        return ""
    return str(s).translate(str.maketrans("０１２３４５６７８９．－＋　", "0123456789.-+ "))


def clean_text(s: str) -> str:
    s = zen_to_han(str(s))
    s = s.replace("\xa0", " ").replace("\r", "\n")
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


@st.cache_data(ttl=900, show_spinner=False)
def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def make_url(page: str, rno: str, jcd: str, hd: str) -> str:
    return f"https://www.boatrace.jp/owpc/pc/race/{page}?rno={rno}&jcd={jcd}&hd={hd}"


def parse_query_from_url(url: str) -> Tuple[str, str, str]:
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    rno = q.get("rno", [""])[0]
    jcd = q.get("jcd", [""])[0].zfill(2)
    hd = q.get("hd", [""])[0]
    if not rno or not jcd or not hd:
        raise ValueError("URLから rno / jcd / hd を取得できませんでした。")
    return rno, jcd, hd


def soup_lines(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return [clean_text(x) for x in soup.get_text("\n").splitlines() if clean_text(x)]


def cell_texts(row) -> List[str]:
    return [clean_text(td.get_text("\n")) for td in row.find_all(["td", "th"])]


def extract_lane_from_text(text: str) -> int:
    m = re.match(r"^([1-6])(?:\s|$|Image)", clean_text(text))
    return int(m.group(1)) if m else 0


def extract_event_name(html: str, place: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text(soup.title.get_text(" ")) if soup.title else ""
    if title:
        title = re.sub(r"出走表.*|オッズ.*|直前情報.*|【.*", "", title)
        title = title.replace("BOAT RACE", "").replace("ボートレース", "").replace(place, "")
        title = title.strip(" -｜|")
        if 5 <= len(title) <= 80 and title not in ["G3", "ヴィーナスシリーズ", "ルーキーシリーズ"]:
            return title
    return ""


def extract_name_from_text(text: str) -> str:
    lines = [clean_text(x) for x in text.splitlines() if clean_text(x)]
    for i, line in enumerate(lines):
        if re.search(r"\d{4}\s*/\s*[AB][12]", line):
            for cand in lines[i + 1:i + 8]:
                if cand and not re.search(r"\d|kg|F\d|L\d|/", cand):
                    if all(x not in cand for x in ["支部", "出身", "年齢", "全国", "当地", "モーター", "ボート"]):
                        return cand.replace(" ", "")
    for line in lines:
        if re.fullmatch(r"[一-龥ぁ-んァ-ヶー]+\s*[一-龥ぁ-んァ-ヶー]+", line):
            return line.replace(" ", "")
    return ""


def extract_reg_class(text: str) -> str:
    m = re.search(r"\d{4}\s*/\s*([AB][12])", text)
    return m.group(1) if m else "B1"


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
        "national_win": get(0), "national_2": get(1), "national_3": get(2),
        "local_win": get(3), "local_2": get(4), "local_3": get(5),
        "motor_2": get(6), "motor_3": get(7),
        "boat_2": get(8), "boat_3": get(9),
    }


def parse_racer_from_text(lane: int, text: str) -> Racer:
    klass = extract_reg_class(text)
    name = extract_name_from_text(text) or f"{lane}号艇"
    stats = parse_stats_from_racer_text(text)
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
        motor_2=stats["motor_2"],
        motor_3=stats["motor_3"],
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
    return [uniq[k] for k in sorted(uniq)], {"event_name": event_name, "method": method}


def parse_beforeinfo(html: str, racers: List[Racer]) -> None:
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


def parse_decimal_odds_only(html: str) -> Dict[str, float]:
    odds = {}
    text = clean_text(BeautifulSoup(html, "html.parser").get_text(" "))
    for m in re.finditer(r"([1-6])[-ー－]([1-6])[-ー－]([1-6])\s+(\d+\.\d+)", text):
        a, b, c, v = m.groups()
        if len({a, b, c}) == 3:
            odds[f"{a}-{b}-{c}"] = safe_float(v)
    for m in re.finditer(r"\b([1-6]{3})\s+(\d+\.\d+)\b", text):
        nums, v = m.groups()
        a, b, c = nums[0], nums[1], nums[2]
        if len({a, b, c}) == 3:
            odds[f"{a}-{b}-{c}"] = safe_float(v)
    return odds


def fetch_and_parse_odds3t(rno: str, jcd: str, hd: str) -> Tuple[Dict[str, float], Dict]:
    url = make_url("odds3t", rno, jcd, hd)
    try:
        html = fetch_html(url)
        odds = parse_decimal_odds_only(html)
        return odds, {"odds_url": url, "odds_count": len(odds), "odds_sample": dict(list(odds.items())[:50])}
    except Exception as e:
        return {}, {"odds_url": url, "odds_count": 0, "odds_sample": {}, "odds_warning": str(e)}


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


def calculate_head_power(racers: List[Racer]) -> List[Racer]:
    ranked = calculate_scores(racers)
    top_score = ranked[0].score if ranked else 0
    displays = [r.display_time for r in racers if r.display_time > 0]
    sts = [r.avg_st for r in racers if r.avg_st > 0]
    avg_display = sum(displays) / max(1, len(displays))
    avg_st = sum(sts) / max(1, len(sts))
    one = next((r for r in racers if r.lane == 1), None)
    one_weak = False
    if one:
        one_weak = (
            one.score < top_score - 8
            or one.avg_st >= 0.19
            or (one.display_time and avg_display and one.display_time > avg_display + 0.08)
            or one.klass == "B1"
        )
    for r in racers:
        hp = 40.0
        hp += max(0, r.score - 85) * 0.75
        hp += {"A1": 11, "A2": 6, "B2": -5}.get(r.klass, 0)
        hp += {1: 12, 2: 5, 3: 4, 4: 4, 5: 1, 6: -2}.get(r.lane, 0)
        if r.avg_st and avg_st:
            if r.avg_st <= avg_st - 0.03:
                hp += 7
            elif r.avg_st <= avg_st - 0.015:
                hp += 4
            elif r.avg_st >= avg_st + 0.03:
                hp -= 5
        if r.display_time and avg_display:
            if r.display_time <= avg_display - 0.06:
                hp += 9
            elif r.display_time <= avg_display - 0.03:
                hp += 5
            elif r.display_time >= avg_display + 0.08:
                hp -= 6
        if r.tenji_st:
            if r.tenji_st <= 0.06:
                hp += 5
            elif r.tenji_st <= 0.10:
                hp += 3
            elif r.tenji_st >= 0.18:
                hp -= 3
        if r.tenji_f:
            hp -= 7
        if r.motor_2 >= 40:
            hp += 6
        elif r.motor_2 >= 35:
            hp += 3
        elif r.motor_2 and r.motor_2 <= 25:
            hp -= 4
        if r.local_2 >= 45:
            hp += 5
        elif r.local_2 >= 35:
            hp += 2
        elif r.local_2 and r.local_2 <= 15:
            hp -= 3
        if one_weak and r.lane in [2, 3, 4, 5]:
            hp += 8
        if r.lane in [4, 5, 6] and r.klass == "A1":
            hp += 8
        if r.lane in [4, 5, 6] and r.display_time and avg_display and r.display_time <= avg_display - 0.04:
            hp += 5
        if r.lane in [4, 5, 6] and r.local_2 >= 45:
            hp += 5
        if r.lane == 6 and not (r.klass == "A1" and r.score >= top_score - 5):
            hp -= 6
        r.head_power = round(max(0, min(100, hp)), 1)
    return sorted(racers, key=lambda x: x.head_power, reverse=True)


def string_power(r: Racer, ranked: List[Racer]) -> float:
    power = 30.0
    if r.display_time and r.display_time <= 7.12:
        power += 10
    elif r.display_time and r.display_time <= 7.18:
        power += 5
    if r.avg_st <= 0.15:
        power += 8
    elif r.avg_st <= 0.17:
        power += 4
    if r.tenji_st:
        if r.tenji_st <= 0.08:
            power += 7
        elif r.tenji_st <= 0.12:
            power += 4
    if r.motor_2 >= 40:
        power += 8
    elif r.motor_2 >= 35:
        power += 5
    if r.boat_2 >= 40:
        power += 4
    if r.local_2 >= 45:
        power += 7
    elif r.local_2 >= 35:
        power += 4
    if r.klass == "A1":
        power += 8
    elif r.klass == "A2":
        power += 4
    score_sorted = sorted(ranked, key=lambda x: x.score, reverse=True)
    bottom_lanes = [x.lane for x in score_sorted[-2:]]
    if r.lane in bottom_lanes:
        power += 8
    if r.lane == 6 and power < 50:
        power -= 5
    return round(max(0, min(100, power)), 1)



def calculate_place_power(racers: List[Racer]) -> List[Racer]:
    """
    相手期待値AI。
    頭ではなく、2着/3着の相手として残す力を評価する。
    AI指数よりも展示・ST・機力・当地・ボートを重視する。
    """
    calculate_scores(racers)
    calculate_head_power(racers)

    displays = [r.display_time for r in racers if r.display_time > 0]
    avg_display = sum(displays) / max(1, len(displays))

    score_sorted = sorted(racers, key=lambda x: x.score, reverse=True)
    bottom_lanes = [x.lane for x in score_sorted[-2:]]
    top_lanes = [x.lane for x in score_sorted[:2]]

    for r in racers:
        pp = 38.0

        # 相手は指数を見すぎない。ただし上位は最低限評価。
        pp += max(0, r.score - 80) * 0.18

        if r.lane in top_lanes:
            pp += 4

        # 下位指数でも相手なら拾う。
        if r.lane in bottom_lanes:
            pp += 10

        # 展示タイム重視。
        if r.display_time and avg_display:
            if r.display_time <= avg_display - 0.08:
                pp += 14
            elif r.display_time <= avg_display - 0.05:
                pp += 10
            elif r.display_time <= avg_display - 0.03:
                pp += 6
            elif r.display_time >= avg_display + 0.09:
                pp -= 5

        # 展示ST・平均ST。
        if r.tenji_st:
            if r.tenji_st <= 0.06:
                pp += 9
            elif r.tenji_st <= 0.10:
                pp += 6
            elif r.tenji_st <= 0.14:
                pp += 3
            elif r.tenji_st >= 0.20:
                pp -= 4

        if r.tenji_f:
            # F表示でも、攻め気配として相手では少し残す。
            pp += 2

        if r.avg_st <= 0.14:
            pp += 8
        elif r.avg_st <= 0.16:
            pp += 5
        elif r.avg_st <= 0.18:
            pp += 2
        elif r.avg_st >= 0.21:
            pp -= 5

        # 機力・ボート・当地。
        if r.motor_2 >= 42:
            pp += 10
        elif r.motor_2 >= 36:
            pp += 7
        elif r.motor_2 >= 30:
            pp += 4
        elif r.motor_2 and r.motor_2 <= 22:
            pp -= 4

        if r.boat_2 >= 42:
            pp += 7
        elif r.boat_2 >= 35:
            pp += 4
        elif r.boat_2 and r.boat_2 <= 22:
            pp -= 2

        if r.local_2 >= 45:
            pp += 8
        elif r.local_2 >= 35:
            pp += 5
        elif r.local_2 >= 25:
            pp += 2
        elif r.local_2 and r.local_2 <= 12:
            pp -= 4

        if r.klass == "A1":
            pp += 6
        elif r.klass == "A2":
            pp += 3

        # 5・6号艇は頭では厳しくても相手なら拾う。
        if r.lane in [5, 6]:
            pp += 4

        r.place_power = round(max(0, min(100, pp)), 1)

    return sorted(racers, key=lambda x: x.place_power, reverse=True)


def calculate_third_power(racers: List[Racer]) -> List[Racer]:
    """
    3着期待値AI。
    相手期待値をベースに、3着で残す力をさらに評価する。
    """
    calculate_scores(racers)
    calculate_head_power(racers)
    calculate_place_power(racers)

    displays = [r.display_time for r in racers if r.display_time > 0]
    avg_display = sum(displays) / max(1, len(displays))

    score_sorted = sorted(racers, key=lambda x: x.score, reverse=True)
    bottom_lanes = [x.lane for x in score_sorted[-2:]]

    for r in racers:
        tp = 30.0
        tp += r.place_power * 0.55

        # 指数下位は3着として強制的に少し底上げ。
        if r.lane in bottom_lanes:
            tp += 12

        # 展示・展示STが良ければ3着残りを強化。
        if r.display_time and avg_display:
            if r.display_time <= avg_display - 0.06:
                tp += 8
            elif r.display_time <= avg_display - 0.03:
                tp += 4

        if r.tenji_st:
            if r.tenji_st <= 0.08:
                tp += 6
            elif r.tenji_st <= 0.12:
                tp += 3

        if r.motor_2 >= 38:
            tp += 5
        elif r.motor_2 >= 32:
            tp += 3

        if r.boat_2 >= 38:
            tp += 4

        if r.local_2 >= 35:
            tp += 4

        # 5・6号艇の3着残りを少し厚くする。
        if r.lane in [5, 6]:
            tp += 4

        r.third_power = round(max(0, min(100, tp)), 1)

    return sorted(racers, key=lambda x: x.third_power, reverse=True)


def tactic_analysis(racers: List[Racer]) -> Dict:
    ranked = calculate_scores(racers)
    head_ranked = calculate_head_power(racers)
    calculate_place_power(racers)
    calculate_third_power(racers)
    by_lane = {r.lane: r for r in racers}
    one = by_lane.get(1)
    two = by_lane.get(2)
    three = by_lane.get(3)
    four = by_lane.get(4)
    in_score = 50.0
    upset_score = 35.0
    hole_score = 35.0
    comments = []
    if one:
        in_score += max(0, one.head_power - 65) * 0.6
        in_score += class_bonus(one.klass) * 0.5
        if one.avg_st <= 0.15:
            in_score += 7
            comments.append("1号艇ST良好")
        elif one.avg_st >= 0.19:
            in_score -= 9
            upset_score += 8
            comments.append("1号艇ST遅め")
        if one.display_time and one.display_time <= 7.10:
            in_score += 7
            comments.append("1号艇展示良好")
        elif one.display_time and one.display_time >= 7.22:
            in_score -= 9
            upset_score += 8
            comments.append("1号艇展示弱め")
        if one.motor_2 >= 38:
            in_score += 4
        elif one.motor_2 and one.motor_2 <= 25:
            in_score -= 7
            upset_score += 6
    if four:
        if four.avg_st <= 0.14:
            upset_score += 6
            hole_score += 5
            comments.append("4カドST注意")
        if four.display_time and four.display_time <= 7.10:
            upset_score += 5
            hole_score += 4
            comments.append("4号艇展示良好")
        if four.head_power >= head_ranked[0].head_power - 5:
            upset_score += 7
            hole_score += 5
            comments.append("4号艇頭期待値上位")
    top_head = head_ranked[0]
    if top_head.lane != 1:
        upset_score += 10
        comments.append(f"{top_head.lane}号艇の頭期待値上位")
    if two and two.head_power >= head_ranked[0].head_power - 6:
        in_score += 2
        comments.append("2号艇相手有力")
    if three and three.head_power >= head_ranked[0].head_power - 6:
        hole_score += 4
        comments.append("3号艇連絡み注意")
    if by_lane.get(1) and by_lane[1].head_power >= head_ranked[0].head_power - 4:
        in_score += 4
    else:
        upset_score += 6
    in_score = round(max(0, min(100, in_score)), 1)
    upset_score = round(max(0, min(100, upset_score)), 1)
    hole_score = round(max(0, min(100, hole_score)), 1)
    if in_score >= 78 and by_lane.get(1) and by_lane[1].head_power >= head_ranked[0].head_power - 5:
        style = "イン逃げ濃厚"
    elif upset_score >= 68:
        style = "1飛び警戒"
    elif hole_score >= 64:
        style = "穴期待"
    else:
        style = "混戦"
    return {
        "展開": style,
        "イン逃げ度": in_score,
        "1飛び警戒": upset_score,
        "穴期待度": hole_score,
        "頭期待1位": f"{top_head.lane}号艇 {top_head.name}",
        "コメント": " / ".join(comments[:5]) if comments else "大きな偏りなし",
    }


def race_confidence(racers: List[Racer]) -> Dict:
    ranked = calculate_scores(racers)
    head_ranked = calculate_head_power(racers)
    tactic = tactic_analysis(racers)
    top = ranked[0]
    second = ranked[1]
    sixth = ranked[5]
    head_top = head_ranked[0]
    top_gap = top.score - second.score
    head_gap = head_ranked[0].head_power - head_ranked[1].head_power
    top3_gap = ranked[2].score - ranked[3].score if len(ranked) >= 4 else 0
    spread = top.score - sixth.score
    data_ok_count = sum(1 for r in racers if "名前OK" in r.data_status and r.national_2 > 0)
    display_ok_count = sum(1 for r in racers if r.display_time > 0)
    confidence = 38
    confidence += max(0, top.score - 88) * 0.35
    confidence += max(0, top_gap) * 1.0
    confidence += max(0, head_gap) * 0.9
    confidence += max(0, top3_gap) * 0.35
    confidence += data_ok_count * 0.8
    confidence += display_ok_count * 0.7
    if tactic["展開"] == "イン逃げ濃厚":
        confidence += 7
    elif tactic["展開"] == "1飛び警戒":
        confidence -= 8
    elif tactic["展開"] == "混戦":
        confidence -= 14
    elif tactic["展開"] == "穴期待":
        confidence -= 5
    if head_top.lane == 1:
        confidence += 2
    if top.klass == "A1" or head_top.klass == "A1":
        confidence += 3
    if top.tenji_f:
        confidence -= 10
    if top_gap < 3:
        confidence -= 8
    if head_gap < 3:
        confidence -= 15
    elif head_gap < 6:
        confidence -= 10
    if spread < 14:
        confidence -= 18
    elif spread < 20:
        confidence -= 12
    if display_ok_count < 6:
        confidence -= 5
    if data_ok_count < 6:
        confidence -= 4
    confidence = round(max(0, min(96, confidence)), 1)
    if confidence >= 92 and head_gap >= 8 and spread >= 25 and data_ok_count >= 6 and display_ok_count >= 6:
        grade = "熱🔥"
    elif confidence >= 84 and head_gap >= 6:
        grade = "厚張り候補"
    elif confidence >= 74:
        grade = "厳選候補"
    elif confidence >= 66:
        grade = "穴期待"
    else:
        grade = "見送り寄り"
    return {
        "confidence": confidence,
        "grade": grade,
        "top_lane": top.lane,
        "top_name": top.name,
        "top_score": top.score,
        "head_lane": head_top.lane,
        "head_name": head_top.name,
        "head_power": head_top.head_power,
        "top_gap": round(top_gap, 1),
        "head_gap": round(head_gap, 1),
        "spread": round(spread, 1),
        "data_ok": data_ok_count,
        "display_ok": display_ok_count,
        "tactic": tactic,
    }


def make_ai_table(racers: List[Racer]) -> pd.DataFrame:
    calculate_scores(racers)
    calculate_head_power(racers)
    calculate_place_power(racers)
    calculate_third_power(racers)
    ranked = sorted(racers, key=lambda x: x.score, reverse=True)
    return pd.DataFrame([{
        "順位": i,
        "艇": r.lane,
        "選手": r.name,
        "級別": r.klass,
        "AI指数": r.score,
        "頭期待値": r.head_power,
        "相手期待値": r.place_power,
        "3着期待値": r.third_power,
        "展示": r.display_time,
        "展示ST": f"{'F' if r.tenji_f else ''}{r.tenji_st:.2f}" if r.tenji_st else 0,
        "平均ST": r.avg_st,
        "全国2連率": r.national_2,
        "当地2連率": r.local_2,
        "モーター2連率": r.motor_2,
        "ボート2連率": r.boat_2,
        "データ状態": r.data_status,
    } for i, r in enumerate(ranked, start=1)])


def combo_score(combo: Tuple[int, int, int], racer_map: Dict[int, Racer], tactic: Dict, odds: Dict[str, float]) -> float:
    a, b, c = combo
    r1, r2, r3 = racer_map[a], racer_map[b], racer_map[c]
    racers = list(racer_map.values())
    ranked = calculate_scores(racers)
    calculate_head_power(racers)
    calculate_place_power(racers)
    calculate_third_power(racers)

    r2_string = string_power(r2, ranked)
    r3_string = string_power(r3, ranked)
    odd = odds.get(f"{a}-{b}-{c}", 0.0)

    # v10.9：頭・相手・3着を役割分離
    s = r1.head_power * 1.02 + r2.place_power * 0.66 + r3.third_power * 0.62
    s += r2_string * 0.10
    s += r3_string * 0.10
    if a == 1:
        s += 4.0
    if tactic["展開"] == "イン逃げ濃厚":
        if a == 1:
            s += 6
        else:
            s -= 2
        if b in [2, 3, 4]:
            s += 3
        if c in [2, 3, 4, 5]:
            s += 2
    elif tactic["展開"] == "1飛び警戒":
        if a == 1:
            s -= 10
        if a in [2, 3, 4, 5]:
            s += 9
        if 1 in [b, c]:
            s += 4
    elif tactic["展開"] == "穴期待":
        if a in [3, 4, 5]:
            s += 8
        if b in [1, 4, 5]:
            s += 3
    if r1.head_power >= 78:
        s += 8
    elif r1.head_power >= 70:
        s += 5
    elif r1.head_power >= 62:
        s += 2
    if r1.klass == "A1":
        s += 5.0
    elif r1.klass == "A2":
        s += 2.0
    for x in [r2, r3]:
        if x.display_time and x.display_time <= 7.12:
            s += 2.0
        if x.tenji_st and x.tenji_st <= 0.08:
            s += 1.5
        if x.head_power >= 70:
            s += 1.5
        if x.place_power >= 75:
            s += 3.0
        elif x.place_power >= 65:
            s += 1.5
        if x.third_power >= 78:
            s += 3.0
        elif x.third_power >= 68:
            s += 1.5
    if a == 6 and r1.head_power < 78:
        s -= 8.0
    if odd > 0:
        if 7.0 <= odd <= 35.0:
            s += 8.0
        elif 35.0 < odd <= 80.0:
            s += 3.0
        elif odd < 5.0:
            s -= 5.0
        elif odd > 100:
            s -= 8.0
    return round(s, 2)


def balance_predictions(df: pd.DataFrame, racers: List[Racer], tactic: Dict, pick_count: int, preset: str) -> pd.DataFrame:
    """
    v10.10 買い目バランスAI。
    ・頭期待値上位を中心にする
    ・指数3〜4位を最低1点ずつ残す
    ・相手期待値/3着期待値で下位艇も拾う
    ・ただし最下位/穴紐の拾いすぎを制限する
    """
    df = df.copy()
    df["頭"] = df["買い目"].astype(str).str.split("-").str[0].astype(int)
    df["2着"] = df["買い目"].astype(str).str.split("-").str[1].astype(int)
    df["3着"] = df["買い目"].astype(str).str.split("-").str[2].astype(int)

    score_ranked = calculate_scores(racers)
    head_ranked = calculate_head_power(racers)
    place_ranked = calculate_place_power(racers)
    third_ranked = calculate_third_power(racers)

    score_order = [r.lane for r in score_ranked]
    mid_lanes = score_order[2:4]      # 指数3位・4位
    bottom_lanes = score_order[-2:]   # 指数5位・6位

    strong_heads = [r.lane for r in head_ranked if r.head_power >= 70]
    if not strong_heads:
        strong_heads = [head_ranked[0].lane]

    place_targets = [r.lane for r in place_ranked if r.place_power >= 60]
    for lane in mid_lanes:
        if lane not in place_targets:
            place_targets.append(lane)

    third_targets = [r.lane for r in third_ranked if r.third_power >= 60]
    for lane in mid_lanes:
        if lane not in third_targets:
            third_targets.append(lane)

    if preset == "的中率重視":
        total = min(pick_count, 6)
        max_head1 = 3
        max_bottom_uses = 1
    elif preset == "標準":
        total = pick_count
        max_head1 = 4
        max_bottom_uses = 2
    else:
        total = max(pick_count, 12)
        max_head1 = 5
        max_bottom_uses = 3

    selected = []
    selected_keys = set()
    head_counts = {i: 0 for i in range(1, 7)}
    bottom_use_count = 0
    mid_use_count = {lane: 0 for lane in mid_lanes}

    def add_row(row, allow_extra_bottom: bool = False) -> bool:
        nonlocal bottom_use_count

        key = row["買い目"]
        if key in selected_keys:
            return False

        head = int(row["頭"])
        second = int(row["2着"])
        third = int(row["3着"])

        if head == 1 and head_counts[1] >= max_head1:
            return False

        contains_bottom = (head in bottom_lanes) or (second in bottom_lanes) or (third in bottom_lanes)
        if contains_bottom and not allow_extra_bottom and bottom_use_count >= max_bottom_uses:
            return False

        selected.append(row)
        selected_keys.add(key)
        head_counts[head] += 1

        if contains_bottom:
            bottom_use_count += 1

        for lane in mid_lanes:
            if head == lane or second == lane or third == lane:
                mid_use_count[lane] = mid_use_count.get(lane, 0) + 1

        return True

    # 1. 頭期待値上位から本線
    for h in strong_heads[:3]:
        if len(selected) >= total:
            break
        cand = df[df["頭"] == h].sort_values("評価", ascending=False)
        for _, row in cand.iterrows():
            if add_row(row):
                break

    # 2. 指数3位・4位を必ず最低1点ずつ残す
    for lane in mid_lanes:
        if len(selected) >= total:
            break

        cand = df[
            (df["頭"] == lane) | (df["2着"] == lane) | (df["3着"] == lane)
        ].sort_values("評価", ascending=False)

        for _, row in cand.iterrows():
            if add_row(row):
                break

    # 3. 相手期待値上位を2着候補として追加
    for h in strong_heads[:2]:
        if len(selected) >= total:
            break
        for p in place_targets[:4]:
            if len(selected) >= total:
                break
            if p == h:
                continue

            cand = df[
                (df["頭"] == h) & (df["2着"] == p)
            ].sort_values("評価", ascending=False)

            for _, row in cand.iterrows():
                if add_row(row):
                    break

    # 4. 3着期待値上位を3着候補として追加
    for t in third_targets[:4]:
        if len(selected) >= total:
            break

        cand = df[df["3着"] == t].sort_values("評価", ascending=False)
        for _, row in cand.iterrows():
            if add_row(row):
                break

    # 5. 足りない分は高評価順で補完
    for _, row in df.sort_values("評価", ascending=False).iterrows():
        if len(selected) >= total:
            break
        add_row(row)

    # 6. それでも足りない場合のみ、最下位制限を緩める
    for _, row in df.sort_values("評価", ascending=False).iterrows():
        if len(selected) >= total:
            break
        add_row(row, allow_extra_bottom=True)

    out = pd.DataFrame(selected).drop(columns=["頭", "2着", "3着"], errors="ignore").reset_index(drop=True)

    labels = []
    for i, row in out.iterrows():
        if i < 2:
            labels.append("熱🔥")
        elif i < 5:
            labels.append("本線")
        elif i < total - 1:
            labels.append("抑え")
        else:
            labels.append("穴")

    out["区分"] = labels
    return out

def generate_predictions(racers: List[Racer], odds: Dict[str, float], pick_count: int = 10, preset: str = "標準") -> pd.DataFrame:
    calculate_scores(racers)
    calculate_head_power(racers)
    calculate_place_power(racers)
    calculate_third_power(racers)
    racer_map = {r.lane: r for r in racers}
    tactic = tactic_analysis(racers)
    rows = []
    for combo in itertools.permutations([1, 2, 3, 4, 5, 6], 3):
        key = f"{combo[0]}-{combo[1]}-{combo[2]}"
        odd = odds.get(key, 0.0)
        rows.append({
            "買い目": key,
            "評価": combo_score(combo, racer_map, tactic, odds),
            "オッズ": odd if odd > 0 else "未取得",
        })
    raw_df = pd.DataFrame(rows).sort_values("評価", ascending=False).reset_index(drop=True)

    conf_info = race_confidence(racers)
    conf = conf_info["confidence"]
    grade = conf_info["grade"]

    # v10.9：判定別に買い目点数を自動調整
    if grade == "熱🔥":
        auto_count = 5
    elif grade == "厚張り候補":
        auto_count = 6
    elif grade == "厳選候補":
        auto_count = 8
    elif grade == "穴期待":
        auto_count = 10
    else:
        auto_count = max(4, min(pick_count, 6))

    if preset == "攻め":
        effective_count = min(max(pick_count, auto_count), 20)
    elif preset == "的中率重視":
        effective_count = min(auto_count, pick_count)
    else:
        effective_count = min(max(auto_count, pick_count), 12)

    df = balance_predictions(raw_df, racers, tactic, effective_count, preset)

    if tactic["展開"] == "混戦":
        df = df.head(max(3, effective_count // 2))

    df["勝負度"] = conf
    df["厚張りAI"] = ""
    if conf >= 84:
        df.loc[df.index[:2], "厚張りAI"] = "候補"
    if conf >= 92:
        df.loc[df.index[:1], "厚張りAI"] = "強"
    return df


@st.cache_data(ttl=900, show_spinner=False)
def detect_today_venues(hd: str) -> List[str]:
    urls = [
        f"https://www.boatrace.jp/owpc/pc/race/index?hd={hd}",
        f"https://www.boatrace.jp/owpc/pc/race/index?hd={hd}&jcd=",
    ]
    found = set()
    for url in urls:
        try:
            html = fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                txt = clean_text(a.get_text(" "))
                m = re.search(r"jcd=(\d{2})", href)
                if m:
                    jcd = m.group(1).zfill(2)
                    if jcd in JCD_MAP and ("racelist" in href or "race" in href or JCD_MAP[jcd] in txt):
                        found.add(jcd)
            text = clean_text(soup.get_text(" "))
            for jcd, place in JCD_MAP.items():
                if place in text:
                    found.add(jcd)
        except Exception:
            pass
    return sorted(found)


@st.cache_data(ttl=900, show_spinner=False)
def analyze_single_race_cached(jcd: str, rno: int, hd: str, use_before: bool, use_odds: bool, pick_count: int, preset: str) -> Dict:
    place = JCD_MAP.get(jcd, jcd)
    racelist_url = make_url("racelist", str(rno), jcd, hd)
    html = fetch_html(racelist_url)
    racers, meta = parse_racelist(html, place)
    if use_before:
        try:
            before_html = fetch_html(make_url("beforeinfo", str(rno), jcd, hd))
            parse_beforeinfo(before_html, racers)
        except Exception:
            pass
    odds = {}
    if use_odds:
        try:
            odds, _ = fetch_and_parse_odds3t(str(rno), jcd, hd)
        except Exception:
            odds = {}
    pred_df = generate_predictions(racers, odds, pick_count, preset)
    conf = race_confidence(racers)
    tactic = conf["tactic"]
    top_picks = " / ".join(pred_df.head(3)["買い目"].astype(str).tolist())
    return {
        "場": place,
        "R": rno,
        "レース": f"{place}{rno}R",
        "勝負度": conf["confidence"],
        "判定": conf["grade"],
        "展開": tactic["展開"],
        "頭期待1位": tactic["頭期待1位"],
        "イン逃げ度": tactic["イン逃げ度"],
        "1飛び警戒": tactic["1飛び警戒"],
        "穴期待度": tactic["穴期待度"],
        "本命": f"{conf['top_lane']}号艇 {conf['top_name']}",
        "頭候補": f"{conf['head_lane']}号艇 {conf['head_name']}",
        "本命指数": conf["top_score"],
        "頭期待値": conf["head_power"],
        "相手期待1位": f"{calculate_place_power(racers)[0].lane}号艇 {calculate_place_power(racers)[0].name}",
        "3着期待1位": f"{calculate_third_power(racers)[0].lane}号艇 {calculate_third_power(racers)[0].name}",
        "上位差": conf["top_gap"],
        "頭期待差": conf["head_gap"],
        "全体差": conf["spread"],
        "展示取得": conf["display_ok"],
        "データ取得": conf["data_ok"],
        "買い目候補": top_picks,
        "URL": racelist_url,
        "開催名": meta.get("event_name", ""),
    }


def build_note_text(event_name: str, place: str, rno: str, ai_df: pd.DataFrame, pred_df: pd.DataFrame, tactic: Dict) -> str:
    lines = []
    title = f"{place}{rno}R"
    if event_name:
        title += f"｜{event_name}"
    lines.append(title)
    lines.append("")
    lines.append(f"展開判定：{tactic['展開']}｜頭期待1位：{tactic['頭期待1位']}")
    lines.append(f"イン逃げ度 {tactic['イン逃げ度']}%｜1飛び警戒 {tactic['1飛び警戒']}%")
    lines.append("")
    lines.append("【指数表・印】")
    marks = ["◎", "○", "▲", "△", "☆", "消"]
    for i, row in ai_df.iterrows():
        mark = marks[i] if i < len(marks) else ""
        lines.append(f"{mark} {int(row['艇'])}号艇 {row['選手']}｜指数 {row['AI指数']}｜頭期待 {row['頭期待値']}｜相手期待 {row.get('相手期待値', 0)}｜3着期待 {row.get('3着期待値', 0)}")
    lines.append("")
    lines.append("【買い目】")
    for _, row in pred_df.iterrows():
        odds_txt = f"（{row['オッズ']}倍）" if isinstance(row["オッズ"], float) else "（オッズ未反映）"
        lines.append(f"{row['区分']} {row['買い目']} {odds_txt}")
    lines.append("")
    lines.append("※指数表・印とは連動していない場合もございます。")
    lines.append("※オッズ未取得の場合は指数・展示・成績・頭期待値を中心に評価しています。")
    return "\n".join(lines)


def run_single_race_view(url: str, use_before: bool, use_odds: bool, pick_count: int, preset: str, debug: bool):
    rno, jcd, hd = parse_query_from_url(url)
    place = JCD_MAP.get(jcd, f"jcd={jcd}")
    racelist_url = make_url("racelist", rno, jcd, hd)
    before_url = make_url("beforeinfo", rno, jcd, hd)
    racelist_html = fetch_html(racelist_url)
    racers, meta = parse_racelist(racelist_html, place)
    if use_before:
        try:
            before_html = fetch_html(before_url)
            parse_beforeinfo(before_html, racers)
        except Exception as e:
            st.warning(f"直前情報の取得に失敗しました: {e}")
    odds = {}
    odds_meta = {}
    if use_odds:
        odds, odds_meta = fetch_and_parse_odds3t(rno, jcd, hd)
    ai_df = make_ai_table(racers)
    pred_df = generate_predictions(racers, odds, pick_count, preset)
    conf = race_confidence(racers)
    tactic = conf["tactic"]
    st.subheader(f"{place} {rno}R")
    if meta.get("event_name"):
        st.write(meta["event_name"])
    col1, col2, col3 = st.columns(3)
    col1.metric("勝負度", f"{conf['confidence']}%")
    col2.metric("展開", tactic["展開"])
    col3.metric("頭期待1位", tactic["頭期待1位"])
    st.info(f"展開コメント：{tactic['コメント']}")
    st.markdown("### 指数表")
    st.dataframe(ai_df, width="stretch", hide_index=True)
    st.markdown("### 買い目AI")
    st.dataframe(pred_df, width="stretch", hide_index=True)
    st.markdown("### Note貼り付け用")
    st.text_area("コピー用", value=build_note_text(meta.get("event_name", ""), place, rno, ai_df, pred_df, tactic), height=320)
    if debug:
        st.markdown("### デバッグ")
        st.code(f"出走表: {racelist_url}\n直前情報: {before_url}")
        st.write("抽出方式:", meta.get("method"))
        st.write("オッズ件数:", len(odds))
        st.write(odds_meta.get("odds_sample", {}))


def init_venue_state(detected: List[str]):
    if "venue_selected" not in st.session_state:
        st.session_state["venue_selected"] = {jcd: (jcd in detected) for jcd in JCD_MAP.keys()}
    elif not any(st.session_state["venue_selected"].values()) and detected:
        st.session_state["venue_selected"] = {jcd: (jcd in detected) for jcd in JCD_MAP.keys()}


def set_all_venues(value: bool):
    st.session_state["venue_selected"] = {jcd: value for jcd in JCD_MAP.keys()}


def set_detected_venues(detected: List[str]):
    st.session_state["venue_selected"] = {jcd: (jcd in detected) for jcd in JCD_MAP.keys()}


def venue_checkbox_selector(detected: List[str]) -> List[str]:
    init_venue_state(detected)
    st.markdown("### チェックする開催場")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("自動検出だけ選択"):
            set_detected_venues(detected)
            st.rerun()
    with col_b:
        if st.button("全選択"):
            set_all_venues(True)
            st.rerun()
    with col_c:
        if st.button("全解除"):
            set_all_venues(False)
            st.rerun()
    cols = st.columns(4)
    for idx, (jcd, place) in enumerate(JCD_MAP.items()):
        with cols[idx % 4]:
            mark = "（開催）" if jcd in detected else ""
            current = st.session_state["venue_selected"].get(jcd, False)
            st.session_state["venue_selected"][jcd] = st.checkbox(f"{place}{mark}", value=current, key=f"venue_{jcd}")
    return [jcd for jcd, selected in st.session_state["venue_selected"].items() if selected]


def compact_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "場", "R", "レース", "勝負度", "判定", "展開",
        "頭期待1位", "イン逃げ度", "1飛び警戒", "穴期待度",
        "本命", "頭候補", "本命指数", "頭期待値", "相手期待1位", "3着期待1位",
        "上位差", "頭期待差", "全体差",
        "展示取得", "データ取得", "買い目候補",
    ]
    return df[[c for c in cols if c in df.columns]]


def detail_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "場", "R", "レース", "勝負度", "判定", "展開",
        "頭期待1位", "本命", "頭候補", "本命指数", "頭期待値", "相手期待1位", "3着期待1位",
        "上位差", "頭期待差", "全体差",
        "買い目候補", "開催名", "URL",
    ]
    return df[[c for c in cols if c in df.columns]]


def show_saved_results(min_conf: int, max_rows: int):
    if "last_results_df" not in st.session_state or st.session_state["last_results_df"] is None:
        st.info("まだ解析結果がありません。開催場を選んで「厳選AIを実行」を押してください。")
        return
    df_all = st.session_state["last_results_df"]
    df_best = df_all[df_all["勝負度"] >= min_conf].sort_values(["勝負度", "頭期待値"], ascending=False).head(max_rows)
    df_hot = df_all[df_all["判定"].isin(["熱🔥", "厚張り候補"])].sort_values(["勝負度", "頭期待値"], ascending=False)
    tab1, tab2, tab3, tab4 = st.tabs(["全レース一覧", "本日の厳選レース", "熱🔥・厚張り", "開催場別"])
    with tab1:
        st.markdown("### 全レース一覧")
        st.dataframe(compact_columns(df_all), width="stretch", hide_index=True)
    with tab2:
        st.markdown("### 本日の厳選レース")
        if len(df_best) == 0:
            st.info("条件に合うレースはありませんでした。最低勝負度を下げてください。")
        else:
            st.dataframe(detail_columns(df_best), width="stretch", hide_index=True)
            hd = st.session_state.get("last_hd", "")
            lines = [f"【本日の厳選レース】{hd}", ""]
            for _, row in df_best.iterrows():
                lines.append(f"{row['判定']}｜{row['レース']}｜勝負度 {row['勝負度']}%｜展開 {row['展開']}｜頭期待 {row['頭期待1位']}｜候補 {row['買い目候補']}")
            lines.append("")
            lines.append("※指数・展示・成績・頭期待値を中心に自動評価しています。")
            lines.append("※指数表・印とは連動していない場合もございます。")
            st.text_area("Note貼り付け用", value="\n".join(lines), height=300)
    with tab3:
        st.markdown("### 熱🔥・厚張り候補")
        if len(df_hot) == 0:
            st.info("熱🔥・厚張り候補はありませんでした。")
        else:
            st.dataframe(detail_columns(df_hot), width="stretch", hide_index=True)
    with tab4:
        st.markdown("### 開催場別")
        place_choice = st.selectbox("開催場を選択", sorted(df_all["場"].unique().tolist()))
        df_place = df_all[df_all["場"] == place_choice].sort_values(["R"])
        df_place_best = df_place[df_place["勝負度"] >= min_conf].sort_values(["勝負度", "頭期待値"], ascending=[False, False])
        st.markdown(f"#### {place_choice} 全レース")
        st.dataframe(compact_columns(df_place), width="stretch", hide_index=True)
        st.markdown(f"#### {place_choice} 厳選レース")
        if len(df_place_best) == 0:
            st.info("この開催場では条件に合う厳選レースがありません。")
        else:
            st.dataframe(detail_columns(df_place_best), width="stretch", hide_index=True)


def run_selection_screen(hd: str, use_before: bool, use_odds: bool, pick_count: int, preset: str):
    st.markdown("### 厳選AI")
    detected = detect_today_venues(hd)
    if detected:
        st.success(f"開催場を自動検出：{len(detected)}場")
        st.write(" / ".join([JCD_MAP[j] for j in detected]))
    else:
        st.warning("開催場の自動検出に失敗しました。手動で選んでください。")
    selected_jcds = venue_checkbox_selector(detected)
    st.divider()
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        min_conf = st.slider("厳選表示の最低勝負度", 0, 100, 74)
    with col_b:
        max_rows = st.slider("厳選最大表示数", 5, 80, 30)
    with col_c:
        race_range = st.slider("巡回R", 1, 12, (1, 12))
    st.info(f"選択中：{len(selected_jcds)}場 / {', '.join([JCD_MAP[j] for j in selected_jcds]) if selected_jcds else 'なし'}")
    col_run, col_clear = st.columns(2)
    with col_run:
        run_button = st.button("厳選AIを実行 / 再解析", type="primary")
    with col_clear:
        if st.button("履歴をクリア"):
            st.session_state["last_results_df"] = None
            st.session_state["last_hd"] = None
            st.rerun()
    if run_button:
        if not selected_jcds:
            st.warning("開催場を選んでください。")
            return
        results = []
        total = len(selected_jcds) * (race_range[1] - race_range[0] + 1)
        progress = st.progress(0)
        status = st.empty()
        count = 0
        for jcd in selected_jcds:
            for rno in range(race_range[0], race_range[1] + 1):
                count += 1
                status.write(f"解析中：{JCD_MAP.get(jcd, jcd)} {rno}R")
                progress.progress(min(1.0, count / max(total, 1)))
                try:
                    result = analyze_single_race_cached(jcd, rno, hd, use_before, use_odds, pick_count, preset)
                    results.append(result)
                except Exception:
                    continue
        progress.empty()
        status.empty()
        if not results:
            st.error("解析できるレースがありませんでした。")
            return
        df_all = pd.DataFrame(results).sort_values(["場", "R"])
        st.session_state["last_results_df"] = df_all
        st.session_state["last_hd"] = hd
        st.success("解析結果を保存しました。予想画面に移動して戻っても残ります。")
    show_saved_results(min_conf, max_rows)


def main():
    st.set_page_config(page_title="BOATRACE AI", page_icon="🚤", layout="wide")
    st.title("🚤 BOATRACE AI")
    st.caption(APP_VERSION)
    if "last_results_df" not in st.session_state:
        st.session_state["last_results_df"] = None
    if "last_hd" not in st.session_state:
        st.session_state["last_hd"] = None
    today = datetime.now(JST).strftime("%Y%m%d")
    st.sidebar.header("共通設定")
    hd = st.sidebar.text_input("日付 hd", value=today)
    st.sidebar.caption("軽量化したい場合は、直前情報OFF・巡回Rを絞るのがおすすめです。")
    use_before = st.sidebar.checkbox("直前情報を取得", value=True)
    use_odds = st.sidebar.checkbox("オッズ取得を試す", value=False)
    preset = st.sidebar.radio("買い目プリセット", ["的中率重視", "標準", "攻め"], index=0)
    if preset == "的中率重視":
        default_count = 5
    elif preset == "標準":
        default_count = 10
    else:
        default_count = 14
    pick_count = st.sidebar.slider("買い目表示点数", 3, 20, default_count)
    debug = st.sidebar.checkbox("デバッグ表示", value=False)
    mode = st.radio("モード", ["厳選AI", "予想"], horizontal=True)
    if mode == "厳選AI":
        run_selection_screen(hd, use_before, use_odds, pick_count, preset)
    else:
        default_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno=2&jcd=20&hd={hd}"
        url = st.text_input("BOATRACE公式 出走表URL", value=default_url)
        if st.button("AI予想を実行", type="primary"):
            run_single_race_view(url, use_before, use_odds, pick_count, preset, debug)
        if st.session_state.get("last_results_df") is not None:
            st.info("厳選AIの前回結果は保存されています。厳選AIに戻ると再解析なしで表示できます。")


if __name__ == "__main__":
    main()
