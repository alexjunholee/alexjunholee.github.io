import json
import unittest
from datetime import datetime, timezone
from update_schedule import build_availability, build_schedule

NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)

def calendar(*events):
    return 'BEGIN:VCALENDAR\n' + ''.join('BEGIN:VEVENT\n' + e + '\nEND:VEVENT\n' for e in events) + 'END:VCALENDAR\n'

class AvailabilityTests(unittest.TestCase):
    def test_public_holidays_are_busy_without_publishing_names(self):
        holiday = 'DTSTART;VALUE=DATE:20260925\nDTEND;VALUE=DATE:20260926\nSUMMARY:추석\nDESCRIPTION:공휴일\nTRANSP:TRANSPARENT'
        substitute = 'DTSTART;VALUE=DATE:20261005\nDTEND;VALUE=DATE:20261006\nSUMMARY:대체공휴일\nTRANSP:TRANSPARENT'
        data = build_schedule(calendar(), calendar(holiday, substitute), NOW)
        self.assertEqual(len(data['busy']), 2)
        self.assertTrue(all(e['allDay'] for e in data['busy']))
        self.assertNotIn('추석', json.dumps(data, ensure_ascii=False))
        self.assertEqual(set(data['busy'][0]), {'start', 'end', 'allDay'})

    def test_holiday_and_existing_all_day_event_remain_separate(self):
        event = 'DTSTART;VALUE=DATE:20260925\nDTEND;VALUE=DATE:20260926'
        data = build_schedule(calendar(event), calendar(event+'\nTRANSP:TRANSPARENT'), NOW)
        self.assertEqual(len(data['busy']), 2)

    def test_only_times_are_published_and_equal_times_remain_separate(self):
        event = 'DTSTART:20260925T040000Z\nDTEND:20260925T080000Z\nSUMMARY:Private meeting\nDESCRIPTION:Confidential\nLOCATION:Private address\nATTENDEE:mailto:guest@example.com\nUID:secret'
        data = build_availability(calendar(event, event), NOW)
        self.assertEqual(len(data['busy']), 2)
        self.assertEqual(set(data['busy'][0]), {'start', 'end', 'allDay'})
        for private in ('Private', 'Confidential', 'guest', 'secret'):
            self.assertNotIn(private, json.dumps(data))

    def test_all_day_and_local_time(self):
        data = build_availability(calendar('DTSTART;VALUE=DATE:20260925\nDTEND;VALUE=DATE:20260928', 'DTSTART;TZID=Asia/Seoul:20260930T133000\nDTEND;TZID=Asia/Seoul:20260930T163000'), NOW)
        self.assertTrue(data['busy'][0]['allDay'])
        self.assertEqual(data['busy'][0]['end'], '2026-09-28T00:00:00+09:00')
        self.assertEqual(data['busy'][1]['start'], '2026-09-30T13:30:00+09:00')

    def test_cancelled_transparent_and_old_events_omitted(self):
        base = 'DTSTART:20260925T040000Z\nDTEND:20260925T080000Z'
        data = build_availability(calendar(base+'\nSTATUS:CANCELLED', base+'\nTRANSP:TRANSPARENT', 'DTSTART:20250925T040000Z\nDTEND:20250925T080000Z'), NOW)
        self.assertEqual(data['busy'], [])

    def test_invalid_responses_do_not_publish_empty_availability(self):
        for raw in ('<html>Error</html>', calendar('DTSTART:20260925T040000Z'), calendar('DTSTART:20260925T040000Z\nDTEND:20260925T080000Z\nRRULE:FREQ=WEEKLY')):
            with self.assertRaises(ValueError):
                build_availability(raw, NOW)

if __name__ == '__main__':
    unittest.main()
