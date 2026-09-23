import json
import requests
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


# ============================================================
# 91.3 AYCLT FM
# AZURACAST SCHEDULE -> XMLTV + JSON
# ============================================================

AZURACAST_BASE_URL = "https://radio.913aycltfm.com"

TIMEZONE = ZoneInfo("America/Chicago")

# Number of days of programming to generate.
DAYS_AHEAD = 365

# IMPORTANT:
# This is your existing XMLTV filename.
XML_OUTPUT = "91.3_Ayclt_ FM_radio_guide.xml"

JSON_OUTPUT = "epg.json"


# ============================================================
# CHANNEL CONFIGURATION
# ============================================================

CHANNELS = [
    {
        "id": "913AycltFM",
        "number": "1",
        "name": "91.3 Ayclt FM",
        "station_id": "91.3_ayclt_fm",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": (
            "https://radio.913aycltfm.com/"
            "static/uploads/91.3_ayclt_fm/"
            "background.1779890712.png"
        ),
    },

    {
        "id": "913AycltFMHD2",
        "number": "1.2",
        "name": "91.3 Ayclt FM HD2",
        "station_id": "91.3_ayclt_fm_hd2",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": (
            "https://radio.913aycltfm.com/"
            "static/uploads/91.3_ayclt_fm_hd2/"
            "background.1779890739.png"
        ),
    },

    {
        "id": "913AycltFMHD3",
        "number": "1.3",
        "name": "91.3 Ayclt FM HD3",
        "station_id": "91.3_ayclt_fm_hd3",
        "description": "Dickinson's Texas #1 Hit Music Station",
        "icon": (
            "https://radio.913aycltfm.com/"
            "static/uploads/91.3_ayclt_fm_hd3/"
            "background.1779890763.png"
        ),
    },

    {
        "id": "913AycltFMLiveStudioCam",
        "number": "1.4",
        "name": "91.3 Ayclt FM Live Studio Cam",
        "station_id": None,
        "description": "91.3 Ayclt FM Live Studio Cam",
        "icon": (
            "https://radio.913aycltfm.com/"
            "static/uploads/91.3_ayclt_fm/"
            "background.1779890712.png"
        ),
    },

    {
        "id": "TheMidWestPlainsman",
        "number": "1.6",
        "name": "The Mid West Plainsman",
        "station_id": None,
        "description": (
            "The Mid West Plainsman Is A Media Broadcast Content "
            "Creator In Waterloo, Iowa Covering Everything In The "
            "Cedar Valley Corridor and Central Iowa"
        ),
        "icon": (
            "https://mp3tourl.com/images/"
            "1790116455920-0030dd1a-85d7-401a-bb1b-8cdb4160da9a.png"
        ),
    },
]


# ============================================================
# HTTP SETTINGS
# ============================================================

REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": "91.3-AYCLT-FM-EPG/1.0",
    "Accept": "application/json",
}


# ============================================================
# AZURACAST API
# ============================================================

def get_schedule(station_id):
    """
    Download the schedule for one AzuraCast station.

    AzuraCast schedule endpoint:
        /api/station/{station_id}/schedule
    """

    url = (
        f"{AZURACAST_BASE_URL}"
        f"/api/station/{station_id}/schedule"
    )

    print()
    print("------------------------------------------")
    print(f"Station: {station_id}")
    print(f"API:     {url}")
    print("------------------------------------------")

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        print(f"HTTP status: {response.status_code}")

        response.raise_for_status()

    except requests.RequestException as error:
        raise RuntimeError(
            f"Could not download AzuraCast schedule "
            f"for {station_id}: {error}"
        ) from error

    try:
        data = response.json()

    except ValueError as error:
        raise RuntimeError(
            f"AzuraCast returned invalid JSON for "
            f"{station_id}."
        ) from error

    # AzuraCast normally returns an array.
    if isinstance(data, list):
        return data

    # Be tolerant of wrapped responses.
    if isinstance(data, dict):

        if isinstance(data.get("data"), list):
            return data["data"]

        if isinstance(data.get("items"), list):
            return data["items"]

        if isinstance(data.get("results"), list):
            return data["results"]

    raise RuntimeError(
        f"Unexpected AzuraCast API response format "
        f"for {station_id}: "
        f"{type(data).__name__}"
    )


# ============================================================
# TIMESTAMP CONVERSION
# ============================================================

def timestamp_to_datetime(value):
    """
    Convert possible AzuraCast timestamp formats
    into a timezone-aware datetime in America/Chicago.
    """

    if value is None:
        return None

    # --------------------------------------------------------
    # Unix timestamp
    # --------------------------------------------------------

    if isinstance(value, (int, float)):

        return datetime.fromtimestamp(
            value,
            timezone.utc,
        ).astimezone(TIMEZONE)

    # --------------------------------------------------------
    # String
    # --------------------------------------------------------

    if isinstance(value, str):

        value = value.strip()

        if not value:
            return None

        # Numeric Unix timestamp
        try:

            if value.isdigit():

                return datetime.fromtimestamp(
                    int(value),
                    timezone.utc,
                ).astimezone(TIMEZONE)

        except (ValueError, OverflowError):
            pass

        # ISO-8601
        try:

            iso_value = value

            if iso_value.endswith("Z"):
                iso_value = iso_value[:-1] + "+00:00"

            dt = datetime.fromisoformat(
                iso_value
            )

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=TIMEZONE
                )

            return dt.astimezone(TIMEZONE)

        except ValueError:
            pass

        # Common SQL datetime format
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
        ]

        for fmt in formats:

            try:

                dt = datetime.strptime(
                    value,
                    fmt,
                )

                return dt.replace(
                    tzinfo=TIMEZONE
                )

            except ValueError:
                continue

    return None


# ============================================================
# XMLTV TIME
# ============================================================

def xmltv_time(dt):
    """
    Convert datetime into XMLTV format.

    Example:
        20260923030000 -0500
    """

    dt = dt.astimezone(TIMEZONE)

    offset = dt.utcoffset()

    if offset is None:
        offset = timedelta(0)

    total_minutes = int(
        offset.total_seconds() / 60
    )

    sign = (
        "+"
        if total_minutes >= 0
        else "-"
    )

    total_minutes = abs(
        total_minutes
    )

    hours = total_minutes // 60
    minutes = total_minutes % 60

    return (
        dt.strftime("%Y%m%d%H%M%S")
        + " "
        + f"{sign}{hours:02d}{minutes:02d}"
    )


# ============================================================
# FIELD HELPER
# ============================================================

def get_field(item, *names):
    """
    Return the first field that exists.
    """

    for name in names:

        if name in item:

            return item[name]

    return None


# ============================================================
# SHOW NAME
# ============================================================

def get_show_name(item, station):
    """
    Find the most useful show/program name.
    """

    name = get_field(
        item,
        "name",
        "title",
        "show_name",
        "streamer_name",
        "playlist_name",
    )

    if isinstance(name, dict):

        name = (
            name.get("name")
            or name.get("title")
        )

    if name:
        return str(name)

    return station["name"]


# ============================================================
# DESCRIPTION
# ============================================================

def get_description(item, station):
    """
    Find a useful description.
    """

    description = get_field(
        item,
        "description",
        "desc",
        "comments",
    )

    if description:
        return str(description)

    return station["description"]


# ============================================================
# CONVERT AZURACAST SCHEDULE
# ============================================================

def convert_schedule(
    station,
    schedule_data,
    start_limit,
    end_limit,
):
    """
    Convert AzuraCast schedule records into internal EPG events.
    """

    events = []

    for item in schedule_data:

        if not isinstance(item, dict):
            continue

        # ----------------------------------------------------
        # START
        # ----------------------------------------------------

        start_value = get_field(
            item,
            "start",
            "start_timestamp",
            "start_time",
            "start_datetime",
        )

        # ----------------------------------------------------
        # END
        # ----------------------------------------------------

        end_value = get_field(
            item,
            "end",
            "end_timestamp",
            "end_time",
            "end_datetime",
        )

        start = timestamp_to_datetime(
            start_value
        )

        end = timestamp_to_datetime(
            end_value
        )

        # ----------------------------------------------------
        # Invalid schedule item
        # ----------------------------------------------------

        if start is None or end is None:
            continue

        if end <= start:
            continue

        # ----------------------------------------------------
        # Ignore events outside EPG window
        # ----------------------------------------------------

        if end <= start_limit:
            continue

        if start >= end_limit:
            continue

        # ----------------------------------------------------
        # Clip to EPG window
        # ----------------------------------------------------

        if start < start_limit:
            start = start_limit

        if end > end_limit:
            end = end_limit

        # ----------------------------------------------------
        # Name / description
        # ----------------------------------------------------

        name = get_show_name(
            item,
            station,
        )

        description = get_description(
            item,
            station,
        )

        # ----------------------------------------------------
        # Create event
        # ----------------------------------------------------

        events.append(
            {
                "channel_id": station["id"],
                "station_name": station["name"],
                "title": name,
                "description": description,
                "start_dt": start,
                "end_dt": end,
                "icon": station["icon"],
            }
        )

    return events


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def remove_duplicate_events(events):

    unique = {}

    for event in events:

        key = (
            event["channel_id"],
            event["start_dt"],
            event["end_dt"],
            event["title"],
        )

        unique[key] = event

    return list(
        unique.values()
    )


# ============================================================
# SORT EVENTS
# ============================================================

def sort_events(events):

    events.sort(
        key=lambda event: (
            event["channel_id"],
            event["start_dt"],
            event["end_dt"],
        )
    )

    return events


# ============================================================
# CREATE FALLBACK EVENTS
# ============================================================

def create_fallback_events(
    station,
    events,
    start_limit,
    end_limit,
):
    """
    Fill gaps between actual AzuraCast events.

    This keeps the EPG continuous while preserving the
    actual scheduled programs returned by AzuraCast.
    """

    if not events:

        return [
            {
                "channel_id": station["id"],
                "station_name": station["name"],
                "title": station["name"],
                "description": station["description"],
                "start_dt": start_limit,
                "end_dt": end_limit,
                "icon": station["icon"],
            }
        ]

    events = sort_events(
        events.copy()
    )

    result = []

    current = start_limit

    for event in events:

        event_start = event["start_dt"]
        event_end = event["end_dt"]

        # ----------------------------------------------------
        # Prevent invalid overlap
        # ----------------------------------------------------

        if event_end <= current:
            continue

        if event_start < current:
            event_start = current
            event["start_dt"] = event_start

        # ----------------------------------------------------
        # Gap before scheduled program
        # ----------------------------------------------------

        if event_start > current:

            result.append(
                {
                    "channel_id": station["id"],
                    "station_name": station["name"],
                    "title": station["name"],
                    "description": station["description"],
                    "start_dt": current,
                    "end_dt": event_start,
                    "icon": station["icon"],
                }
            )

        # ----------------------------------------------------
        # Actual AzuraCast event
        # ----------------------------------------------------

        result.append(event)

        if event_end > current:
            current = event_end

        if current >= end_limit:
            break

    # --------------------------------------------------------
    # Gap after final scheduled event
    # --------------------------------------------------------

    if current < end_limit:

        result.append(
            {
                "channel_id": station["id"],
                "station_name": station["name"],
                "title": station["name"],
                "description": station["description"],
                "start_dt": current,
                "end_dt": end_limit,
                "icon": station["icon"],
            }
        )

    return result


# ============================================================
# BUILD XMLTV
# ============================================================

def build_xmltv(events):

    tv = ET.Element(
        "tv",
        {
            "generator-info-name": "RadioEPG"
        },
    )

    # --------------------------------------------------------
    # CHANNELS
    # --------------------------------------------------------

    for channel in CHANNELS:

        channel_element = ET.SubElement(
            tv,
            "channel",
            {
                "id": channel["id"]
            },
        )

        display_number = ET.SubElement(
            channel_element,
            "display-name",
        )

        display_number.text = (
            channel["number"]
        )

        display_name = ET.SubElement(
            channel_element,
            "display-name",
        )

        display_name.text = (
            channel["name"]
        )

    # --------------------------------------------------------
    # PROGRAMMES
    # --------------------------------------------------------

    for event in events:

        programme = ET.SubElement(
            tv,
            "programme",
            {
                "start": xmltv_time(
                    event["start_dt"]
                ),
                "stop": xmltv_time(
                    event["end_dt"]
                ),
                "channel": event[
                    "channel_id"
                ],
            },
        )

        title = ET.SubElement(
            programme,
            "title",
            {
                "lang": "en"
            },
        )

        title.text = event["title"]

        desc = ET.SubElement(
            programme,
            "desc",
            {
                "lang": "en"
            },
        )

        desc.text = event["description"]

        ET.SubElement(
            programme,
            "icon",
            {
                "src": event["icon"]
            },
        )

    # --------------------------------------------------------
    # Pretty print
    # --------------------------------------------------------

    try:

        ET.indent(
            tv,
            space="  "
        )

    except AttributeError:
        pass

    return ET.tostring(
        tv,
        encoding="unicode",
    )


# ============================================================
# BUILD JSON
# ============================================================

def build_json(events):

    output = []

    for event in events:

        output.append(
            {
                "channel_id": event[
                    "channel_id"
                ],
                "station_name": event[
                    "station_name"
                ],
                "title": event[
                    "title"
                ],
                "description": event[
                    "description"
                ],
                "start": event[
                    "start_dt"
                ].isoformat(),
                "end": event[
                    "end_dt"
                ].isoformat(),
                "icon": event[
                    "icon"
                ],
            }
        )

    return json.dumps(
        output,
        indent=2,
        ensure_ascii=False,
    )


# ============================================================
# WRITE XML
# ============================================================

def write_xml(
    xml_output
):

    with open(
        XML_OUTPUT,
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            '<?xml version="1.0" encoding="utf-8"?>\n'
        )

        file.write(
            '<!DOCTYPE tv SYSTEM "xmltv.dtd">\n'
        )

        file.write(
            xml_output
        )

        file.write("\n")


# ============================================================
# WRITE JSON
# ============================================================

def write_json(
    json_output
):

    with open(
        JSON_OUTPUT,
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            json_output
        )

        file.write("\n")


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "=============================================="
    )
    print(
        "91.3 AYCLT FM AZURACAST EPG GENERATOR"
    )
    print(
        "=============================================="
    )

    # --------------------------------------------------------
    # Current time
    # --------------------------------------------------------

    now = datetime.now(
        TIMEZONE
    )

    # Start at today's midnight.
    start_limit = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    # Generate 365 days.
    end_limit = (
        start_limit
        + timedelta(
            days=DAYS_AHEAD
        )
    )

    print(
        f"Timezone: {TIMEZONE}"
    )

    print(
        f"Start:    {start_limit}"
    )

    print(
        f"End:      {end_limit}"
    )

    print(
        f"Days:     {DAYS_AHEAD}"
    )

    all_events = []

    # --------------------------------------------------------
    # Process stations
    # --------------------------------------------------------

    for station in CHANNELS:

        station_id = station[
            "station_id"
        ]

        # ----------------------------------------------------
        # Stations without an AzuraCast API
        # ----------------------------------------------------

        if not station_id:

            print()
            print(
                f"No AzuraCast station ID for:"
            )

            print(
                f"  {station['name']}"
            )

            # Live Studio Cam and Mid West Plainsman
            # remain continuous blocks because they are
            # not connected to an AzuraCast station schedule.
            fallback = {
                "channel_id": station["id"],
                "station_name": station["name"],
                "title": station["name"],
                "description": station[
                    "description"
                ],
                "start_dt": start_limit,
                "end_dt": end_limit,
                "icon": station["icon"],
            }

            all_events.append(
                fallback
            )

            continue

        # ----------------------------------------------------
        # Download AzuraCast schedule
        # ----------------------------------------------------

        schedule = get_schedule(
            station_id
        )

        print(
            f"Schedule entries received: "
            f"{len(schedule)}"
        )

        # ----------------------------------------------------
        # Convert schedule
        # ----------------------------------------------------

        events = convert_schedule(
            station,
            schedule,
            start_limit,
            end_limit,
        )

        print(
            f"Valid EPG events: "
            f"{len(events)}"
        )

        # ----------------------------------------------------
        # Remove duplicate events
        # ----------------------------------------------------

        events = remove_duplicate_events(
            events
        )

        # ----------------------------------------------------
        # Sort
        # ----------------------------------------------------

        events = sort_events(
            events
        )

        # ----------------------------------------------------
        # Fill uncovered periods
        # ----------------------------------------------------

        events = create_fallback_events(
            station,
            events,
            start_limit,
            end_limit,
        )

        print(
            f"Final EPG blocks: "
            f"{len(events)}"
        )

        all_events.extend(
            events
        )

    # --------------------------------------------------------
    # Sort all channels
    # --------------------------------------------------------

    all_events = sort_events(
        all_events
    )

    # --------------------------------------------------------
    # XMLTV
    # --------------------------------------------------------

    xml_output = build_xmltv(
        all_events
    )

    write_xml(
        xml_output
    )

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    json_output = build_json(
        all_events
    )

    write_json(
        json_output
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print(
        "=============================================="
    )

    print(
        "EPG GENERATION COMPLETE"
    )

    print(
        "=============================================="
    )

    print(
        f"Channels: {len(CHANNELS)}"
    )

    print(
        f"Events:   {len(all_events)}"
    )

    print(
        f"Created:  {XML_OUTPUT}"
    )

    print(
        f"Created:  {JSON_OUTPUT}"
    )

    print(
        "=============================================="
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
