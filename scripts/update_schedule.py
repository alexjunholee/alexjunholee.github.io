"""Build a public availability file containing start/end times only."""
import argparse
import json
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

PUBLIC_FEED = 'https://calendar.google.com/calendar/ical/alexjunholee%40gmail.com/public/basic.ics'
HOLIDAY_FEED = 'https://calendar.google.com/calendar/ical/ko.south_korea.official%23holiday%40group.v.calendar.google.com/public/basic.ics'
KST = ZoneInfo('Asia/Seoul')


def parse_date(line):
    name, value = line.split(':', 1)
    if 'VALUE=DATE' in name:
        return datetime.strptime(value, '%Y%m%d').replace(tzinfo=KST), True
    zone = re.search(r'TZID=([^;:]+)', name)
    if value.endswith('Z'):
        return datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc), False
    return datetime.strptime(value, '%Y%m%dT%H%M%S').replace(tzinfo=ZoneInfo(zone.group(1)) if zone else KST), False


def build_availability(ical, now, *, include_transparent=False):
    unfolded = re.sub(r'\r?\n[ \t]', '', ical)
    if not unfolded.startswith('BEGIN:VCALENDAR') or 'END:VCALENDAR' not in unfolded:
        raise ValueError('Invalid calendar response')
    today = now.astimezone(KST).date()
    start = datetime.combine(today - timedelta(days=today.weekday()), time(), KST)
    end = start + timedelta(days=35)
    busy = []
    for block in re.findall(r'BEGIN:VEVENT\r?\n(.*?)END:VEVENT', unfolded, re.S):
        lines = block.splitlines()
        if 'STATUS:CANCELLED' in lines or ('TRANSP:TRANSPARENT' in lines and not include_transparent):
            continue
        if any(line.startswith('RRULE:') for line in lines):
            raise ValueError('Expected expanded public busy intervals')
        begin = next((x for x in lines if re.match(r'DTSTART[;:]', x)), None)
        finish = next((x for x in lines if re.match(r'DTEND[;:]', x)), None)
        if not begin or not finish:
            raise ValueError('Busy interval missing start or end')
        a, all_day = parse_date(begin)
        b, _ = parse_date(finish)
        if b <= a:
            raise ValueError('Invalid busy interval')
        if b <= start or a >= end:
            continue
        # Publish only times. Never copy names, descriptions, locations or IDs.
        item = {'start': a.isoformat(), 'end': b.isoformat(), 'allDay': all_day}
        busy.append(item)
    return {'generatedAt': now.isoformat(), 'windowStart': start.isoformat(), 'windowEnd': end.isoformat(),
            'busy': sorted(busy, key=lambda event: event['start'])}


def build_schedule(ical, holidays, now):
    data = build_availability(ical, now)
    # Google marks holidays as transparent; this site intentionally blocks them.
    holiday_data = build_availability(holidays, now, include_transparent=True)
    if any(not event['allDay'] for event in holiday_data['busy']):
        raise ValueError('Expected all-day public holidays')
    data['busy'] = sorted(data['busy'] + holiday_data['busy'], key=lambda event: event['start'])
    return data


def read_feed(url):
    request = Request(url, headers={'User-Agent': 'Schedule availability updater'})
    with urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8-sig')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path)
    parser.add_argument('--holidays-input', type=Path)
    parser.add_argument('--output', type=Path, default=Path('schedule.json'))
    args = parser.parse_args()
    raw = args.input.read_text() if args.input else read_feed(PUBLIC_FEED)
    holidays = args.holidays_input.read_text() if args.holidays_input else read_feed(HOLIDAY_FEED)
    data = build_schedule(raw, holidays, datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
    print('Updated public availability: %d intervals' % len(data['busy']))
