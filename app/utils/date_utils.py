from datetime import datetime, timedelta, timezone

# Nicaragua (Managua) is UTC-6, no daylight saving time
NICARAGUA_TZ = timezone(timedelta(hours=-6))

def nicaragua_now():
    """Returns the current naive datetime in Nicaragua time zone."""
    return datetime.utcnow() - timedelta(hours=6)
