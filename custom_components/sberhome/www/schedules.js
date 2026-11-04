// The simple editor recognizes a strict subset; untouched TIME remains opaque.
export const DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];
const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const owns = (value, key) => Object.hasOwn(value, key);

function validZone(zone) {
  try {
    new Intl.DateTimeFormat("en-GB", {timeZone: zone}).format(0);
    return typeof zone === "string" && zone.length > 0;
  } catch {
    return false;
  }
}

function validStart(start) {
  const match = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/.exec(start);
  if (!match) return false;
  const [year, month, day, hour, minute, second] = match.slice(1).map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  date.setUTCHours(hour, minute, second, 0);
  return year > 0 && date.getUTCFullYear() === year && date.getUTCMonth() === month - 1
    && date.getUTCDate() === day && date.getUTCHours() === hour
    && date.getUTCMinutes() === minute && date.getUTCSeconds() === second;
}

export function parseSchedule(rrule, timezone = null) {
  if (typeof rrule !== "string") return null;
  const match = /^DTSTART;TZID=([A-Za-z0-9_+/-]+):(\d{8}T\d{6})\nRRULE:FREQ=DAILY;WKST=MO;BYDAY=([A-Z,]+);BYHOUR=(\d{1,2});BYMINUTE=(\d{1,2});BYSECOND=0$/.exec(rrule);
  if (!match || match[0] !== rrule) return null;
  const [, zone, start, byday, hours, minutes] = match;
  const days = byday.split(","), hour = Number(hours), minute = Number(minutes);
  if ((timezone !== null && timezone !== zone) || !validZone(zone) || !validStart(start)
      || new Set(days).size !== days.length || days.some((day) => !DAYS.includes(day))
      || hour > 23 || minute > 59) return null;
  return {timezone: zone, start, days, hour, minute};
}

function originalSchedule(raw, timezone) {
  if (!object(raw) || raw.type !== "TIME" || !object(raw.time_data)
      || Object.entries(raw).some(([key, value]) => !["type", "time_data"].includes(key) && value !== null)
      || Object.keys(raw.time_data).some((key) => !["rrule", "execute_at"].includes(key))
      || raw.time_data.execute_at != null) return null;
  return parseSchedule(raw.time_data.rrule, timezone);
}

export function editableSchedule(trigger, timezone) {
  const data = trigger.data || {}, parsed = parseSchedule(data.rrule, timezone);
  if (!parsed) return null;
  if (!owns(data, "_raw")) return parsed;
  const original = originalSchedule(data._raw, timezone);
  return original && original.start === parsed.start && original.timezone === parsed.timezone ? parsed : null;
}

export function scheduleError(trigger, timezone) {
  const data = trigger.data || {};
  if (owns(data, "_raw")) {
    const raw = data._raw;
    if (!object(raw) || raw.type !== "TIME") return "schedules.invalid";
    const previous = object(raw.time_data) ? raw.time_data : {};
    if (owns(data, "rrule") === owns(previous, "rrule")
        && JSON.stringify(data.rrule) === JSON.stringify(previous.rrule)) return null;
    if (!originalSchedule(raw, timezone)) return "schedules.read_only";
  }
  if (!parseSchedule(data.rrule, timezone)) return "schedules.invalid";
  return editableSchedule(trigger, timezone) ? null : "schedules.read_only";
}

export function buildSchedule(days, hour, minute, timezone, start = null) {
  if (!Array.isArray(days) || !days.length || new Set(days).size !== days.length
      || days.some((day) => !DAYS.includes(day)) || !Number.isInteger(hour) || hour < 0 || hour > 23
      || !Number.isInteger(minute) || minute < 0 || minute > 59 || !validZone(timezone)) return null;
  if (start === null) {
    const parts = new Intl.DateTimeFormat("en-GB", {timeZone: timezone, year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"}).formatToParts(new Date());
    const get = (type) => parts.find((part) => part.type === type).value;
    start = `${get("year")}${get("month")}${get("day")}T${get("hour")}${get("minute")}${get("second")}`;
  }
  if (!validStart(start)) return null;
  return `DTSTART;TZID=${timezone}:${start}\nRRULE:FREQ=DAILY;WKST=MO;BYDAY=${DAYS.filter((day) => days.includes(day)).join(",")};BYHOUR=${hour};BYMINUTE=${minute};BYSECOND=0`;
}
