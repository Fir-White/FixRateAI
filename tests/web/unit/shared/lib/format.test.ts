import {afterEach,expect,it,vi} from 'vitest';
import {formatDate,formatDateTime,todayAt} from '@/shared/lib/format';
import {dateTimeFormatter} from '@/shared/lib/dateTimeFormatter';

afterEach(()=>vi.useRealTimers());

it('reuses formatters without sharing different timezones or date options',()=>{
 const utc=dateTimeFormatter('ru-RU',{timeZone:'UTC',hour:'2-digit',minute:'2-digit'});
 expect(dateTimeFormatter('ru-RU',{minute:'2-digit',hour:'2-digit',timeZone:'UTC'})).toBe(utc);
 expect(dateTimeFormatter('ru-RU',{timeZone:'Asia/Yekaterinburg',hour:'2-digit',minute:'2-digit'})).not.toBe(utc);
 expect(dateTimeFormatter('ru-RU',{timeZone:'UTC',day:'2-digit'})).not.toBe(utc);
});

it('keeps calendar dates independent of offset and formats timestamps in the site zone',()=>{
  expect(formatDate('2026-11-02')).toContain('02');
  const stamp='2026-11-01T22:30:00Z';
  expect(formatDateTime(stamp,'Asia/Yekaterinburg')).toContain('03:30');
  expect(formatDateTime(stamp,'Europe/Berlin')).toContain('23:30');
  expect(formatDateTime(stamp,'UTC')).toContain('22:30');
});

it('chooses the local date for defaults at the UTC day boundary',()=>{
  vi.useFakeTimers();vi.setSystemTime(new Date('2026-12-31T22:30:00Z'));
  expect(todayAt('Asia/Yekaterinburg')).toBe('2027-01-01');
  expect(todayAt('America/New_York')).toBe('2026-12-31');
});
