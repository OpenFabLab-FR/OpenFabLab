"""Private planning projection shared by the calendar and Résumé."""
from datetime import date
from localized_formats import calendar_moment


def billing_events(db, start, end, include_linked=False):
    """Records without a calendar service or booking already representing them."""
    return db.execute('''SELECT id,title,billing_type,activity_date,activity_start_time,activity_end_time,
        rental_end_date,quote_signed_at,invoice_number,quote_cancelled_at,handed_over_at,returned_at
        FROM billing_records b WHERE activity_date<? AND COALESCE(NULLIF(rental_end_date,''),activity_date)>=?
        AND quote_cancelled_at IS NULL AND NOT EXISTS(SELECT 1 FROM fablab_services s WHERE s.id=b.service_id
            AND (NOT ? OR s.service_type='animation'))
        AND NOT EXISTS(SELECT 1 FROM resource_bookings r WHERE r.billing_record_id=b.id)
        ORDER BY activity_date,activity_start_time,id''', (str(end),str(start),int(include_linked))).fetchall()


def booking_time(day, value, zone):
    try:
        return calendar_moment(str(date.fromisoformat(day)) + 'T' + value,zone)
    except (TypeError,ValueError):
        return None


def billing_confirmed(row):
    return bool(row['quote_signed_at'] or row['invoice_number'] or row['handed_over_at'])
