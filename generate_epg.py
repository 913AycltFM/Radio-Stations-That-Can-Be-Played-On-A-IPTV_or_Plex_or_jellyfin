import json
from datetime import datetime, timedelta
from pathlib import Path
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


# ============================================================
# 91.3 AYCLT FM - AZURACAST XMLTV EPG GENERATOR
# Automatic DJ Schedule + Gap Filling
# ============================================================

AZURACAST_BASE_URL = "https://radio.913aycltfm.com"
TIMEZONE = ZoneInfo("America/Chicago")
DAYS_AHEAD = 7
XML_OUTPUT = "91.3_Ayclt_FM_radio_guide.xml"
JSON_OUTPUT = "epg.json"

STATIONS = {
    "913AycltFM": "91.3_ayclt_fm",
    "913AycltFMHD2": "91.3_ayclt_fm_hd2",
    "913AycltFMHD3": "91.3_ayclt_fm_hd3",
}

CHANNELS = [
    {
        "id": "913AycltFM",
        "display": "1",
        "name": "91.3 Ayclt FM",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm/background.1779890712.png",
    },
    {
        "id": "913AycltFMHD2",
        "display": "1.2",
        "name": "91.3 Ayclt FM HD2",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm_hd2/background.1779890739.png",
    },
    {
        "id": "913AycltFMHD3",
        "display": "1.3",
        "name": "91.3 Ayclt FM HD3",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm_hd3/background.1779890763.png",
    },
    {
        "id": "913AycltFMLiveStudioCam",
        "display": "1.4",
        "name": "91.3 Ayclt FM Live Studio Cam",
        "description": "91.3 Ayclt FM Live Studio Cam",
        "icon": "https://radio.913aycltfm.com/static/uploads/91.3_ayclt_fm/background.1779890712.png",
    },
    {
        "id": "TheMidWestPlainsman",
        "display": "1.5",
        "name": "The Mid West Plainsman",
        "description": "The Mid West Plainsman Is A Media Broadcast Content Creator In Waterloo, Iowa Covering Everything In The Cedar Valley Corridor and Central Iowa",
        "icon": "https://mp3tourl.com/images/1790116455920-0030dd1a-85d7-401a-bb1b-8cdb4160da9a.png",
    },
]


def fetch_json(url):
    print(f"Fetching API: {url}")
    request = Request(url, headers={"User-Agent": "91.3-Ayclt-FM-EPG/1.0", "Accept": "application/json"})
    max_attempts = 3
    retry_delays = (2, 5)
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except HTTPError as error:
            if error.code not in (429,) and not 500 <= error.code <= 599:
                raise RuntimeError(f"AzuraCast API HTTP error {error.code}: {url}") from error
            if attempt == max_attempts:
                raise RuntimeError(f"AzuraCast API HTTP error {error.code} after {max_attempts} attempts: {url}") from error
            time.sleep(retry_delays[attempt - 1])
        except URLError as error:
            if attempt == max_attempts:
                raise RuntimeError(f"AzuraCast API connection error after {max_attempts} attempts: {error.reason}") from error
            time.sleep(retry_delays[attempt - 1])
        except json.JSONDecodeError as error:
            raise RuntimeError(f"AzuraCast API returned invalid JSON: {url}") from error
        except Exception as error:
            raise RuntimeError(f"AzuraCast API request failed: {error}") from error


def find_schedule_list(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    keys = ["schedule", "schedules", "data", "items", "results"]
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested_key in keys:
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return nested
    return []


def get_field(item, names):
    if not isinstance(item, dict):
        return None
    for name in names:
        if name in item and item[name] is not None:
            return item[name]
    return None


def parse_datetime(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=ZoneInfo("UTC")).astimezone(TIMEZONE)
        except Exception:
            return None
    value = str(value).strip()
    if not value:
        return None
    if value.isdigit():
        try:
            timestamp = int(value)
            if timestamp > 100000000000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=ZoneInfo("UTC")).astimezone(TIMEZONE)
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TIMEZONE)
        return dt.astimezone(TIMEZONE)
    except Exception:
        pass
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"]:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=TIMEZONE)
        except Exception:
            continue
    return None


def xmltv_datetime(dt):
    dt = dt.astimezone(TIMEZONE)
    offset = dt.utcoffset() or timedelta(0)
    minutes = int(offset.total_seconds() / 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"{dt:%Y%m%d%H%M%S} {sign}{minutes // 60:02d}{minutes % 60:02d}"


def get_program_title(item, channel_name):
    value = get_field(item, ["name", "title", "program_name", "show_name", "playlist_name", "streamer_name", "dj_name"])
    if isinstance(value, dict):
        value = get_field(value, ["name", "title"])
    return str(value).strip() if value else channel_name


def is_live_program(item):
    """Return True when an AzuraCast schedule entry represents a DJ/streamer."""
    streamer = get_field(item, ["streamer_name", "streamer", "dj_name", "dj", "presenter_name", "presenter"])
    if isinstance(streamer, dict):
        streamer = get_field(streamer, ["name", "title", "display_name"])
    if streamer and str(streamer).strip():
        return True
    description = get_field(item, ["description", "desc"])
    if description:
        description = str(description).strip()
        if description.lower().startswith(("streamer:", "live dj:")):
            return bool(description.split(":", 1)[1].strip())
    return False


def get_description(item, channel_description):
    value = get_field(item, ["description", "desc"])
    if value:
        text = str(value).strip()
        if text.lower().startswith("streamer:"):
            return "Live DJ:" + text.split(":", 1)[1]
        return text
    return channel_description


def fetch_station_schedule(station_slug, start_date, end_date):
    schedules = []
    current_date = start_date
    while current_date <= end_date:
        chunk_end = min(current_date + timedelta(days=6), end_date)
        query = urlencode({"start": current_date.isoformat(), "end": chunk_end.isoformat()})
        url = f"{AZURACAST_BASE_URL}/api/station/{station_slug}/schedule?{query}"
        data = fetch_json(url)
        chunk = find_schedule_list(data)
        schedules.extend(chunk)
        current_date = chunk_end + timedelta(days=1)
    return schedules


def convert_schedule(channel, schedules, minimum, maximum):
    events = []
    for item in schedules:
        if not isinstance(item, dict):
            continue
        start = parse_datetime(get_field(item, ["start", "start_time", "start_datetime", "startDateTime", "starts_at", "start_at"]))
        end = parse_datetime(get_field(item, ["end", "end_time", "end_datetime", "endDateTime", "ends_at", "end_at"]))
        if start is None or end is None or end <= start or end < minimum or start > maximum:
            continue
        start = max(start, minimum)
        end = min(end, maximum)
        events.append({
            "channel_id": channel["id"],
            "channel_name": channel["name"],
            "title": get_program_title(item, channel["name"]),
            "description": get_description(item, channel["description"]),
            "start": start,
            "end": end,
            "icon": channel["icon"],
            "fallback": False,
            "live_program": is_live_program(item),
        })
    return events


def add_filler_blocks(result, channel, start_time, end_time):
    current = start_time
    block_size = timedelta(hours=1)
    utc = ZoneInfo("UTC")
    while current < end_time:
        current_utc = current.astimezone(utc)
        block_end_utc = min(current_utc + block_size, end_time.astimezone(utc))
        block_end = block_end_utc.astimezone(TIMEZONE)
        result.append({
            "channel_id": channel["id"],
            "channel_name": channel["name"],
            "title": channel["name"],
            "description": channel["description"],
            "start": current,
            "end": block_end,
            "icon": channel["icon"],
            "fallback": True,
            "live_program": False,
        })
        current = block_end


def fill_schedule_gaps(channel, events, start_time, end_time):
    result = []
    scheduled = []
    for event in events:
        event_start = max(event["start"], start_time)
        event_end = min(event["end"], end_time)
        if event_end <= event_start:
            continue
        normalized = dict(event)
        normalized["start"] = event_start
        normalized["end"] = event_end
        normalized["fallback"] = False
        scheduled.append(normalized)
    scheduled.sort(key=lambda x: (x["start"], -(x["end"] - x["start"]).total_seconds(), x["title"]))
    real_events = []
    for event in scheduled:
        event_start = event["start"]
        event_end = event["end"]
        if real_events and event_start < real_events[-1]["end"]:
            previous = real_events[-1]
            if event_start == previous["start"]:
                if event_end > previous["end"]:
                    real_events[-1] = event
                continue
            event_start = previous["end"]
            if event_end <= event_start:
                continue
            event = dict(event)
            event["start"] = event_start
        real_events.append(event)
    current = start_time
    for event in real_events:
        if event["start"] > current:
            add_filler_blocks(result, channel, current, event["start"])
        if event["end"] <= current:
            continue
        actual_event = dict(event)
        actual_event["start"] = max(event["start"], current)
        actual_event["end"] = event["end"]
        actual_event["fallback"] = False
        result.append(actual_event)
        current = event["end"]
    if current < end_time:
        add_filler_blocks(result, channel, current, end_time)
    return result


def create_no_schedule_channel(channel, start_time, end_time):
    return [{
        "channel_id": channel["id"],
        "channel_name": channel["name"],
        "title": channel["name"],
        "description": channel["description"],
        "start": start_time,
        "end": end_time,
        "icon": channel["icon"],
        "fallback": True,
        "live_program": False,
    }]


def clean_events(events):
    events.sort(key=lambda event: (event["channel_id"], event["start"], event["end"], event["title"]))
    cleaned = []
    seen = set()
    for event in events:
        key = (event["channel_id"], event["start"].isoformat(), event["end"].isoformat(), event["title"])
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(event)
    return cleaned


def validate_timelines(events):
    grouped = {}
    for event in events:
        grouped.setdefault(event["channel_id"], []).append(event)
    errors = []
    for channel_id, channel_events in grouped.items():
        channel_events.sort(key=lambda event: (event["start"], event["end"]))
        previous = None
        for event in channel_events:
            if event["end"] <= event["start"]:
                errors.append(f"{channel_id}: invalid interval {event['start']} -> {event['end']}")
            if previous is not None and event["start"] < previous["end"]:
                errors.append(f"{channel_id}: overlap between '{previous['title']}' and '{event['title']}'")
            previous = event
    if errors:
        print("TIMELINE VALIDATION FAILED:")
        for error in errors:
            print(f"  - {error}")
        return False
    print(f"Timeline validation successful: {len(grouped)} channels checked; no overlapping programmes.")
    return True


def generate_xml(events):
    root = ET.Element("tv", {"generator-info-name": "RadioEPG"})
    for channel in CHANNELS:
        channel_element = ET.SubElement(root, "channel", {"id": channel["id"]})
        ET.SubElement(channel_element, "display-name").text = channel["display"]
        ET.SubElement(channel_element, "display-name").text = channel["name"]

    for event in events:
        programme = ET.SubElement(root, "programme", {
            "start": xmltv_datetime(event["start"]),
            "stop": xmltv_datetime(event["end"]),
            "channel": event["channel_id"],
        })
        ET.SubElement(programme, "title", {"lang": "en"}).text = event["title"]
        ET.SubElement(programme, "desc", {"lang": "en"}).text = event["description"]

        # Jellyfin maps the XMLTV <live /> element to ProgramInfo.IsLive.
        # Do not add a LIVE category; the native live element is the marker.
        if event.get("live_program"):
            ET.SubElement(programme, "live")

        if event.get("icon"):
            ET.SubElement(programme, "icon", {"src": event["icon"]})

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass
    tree = ET.ElementTree(root)
    path = Path(XML_OUTPUT)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    xml = path.read_text(encoding="utf-8")
    xml = xml.replace('<?xml version=\'1.0\' encoding=\'utf-8\'?>', '<?xml version="1.0" encoding="utf-8"?>', 1)
    if "<!DOCTYPE tv SYSTEM" not in xml:
        xml = xml.replace('<?xml version="1.0" encoding="utf-8"?>', '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE tv SYSTEM "xmltv.dtd">', 1)
    path.write_text(xml, encoding="utf-8")
    print(f"Created: {XML_OUTPUT}")
