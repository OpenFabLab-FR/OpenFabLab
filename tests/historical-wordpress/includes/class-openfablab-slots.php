<?php
if (!defined('ABSPATH')) { exit; }

/** Slot catalogue lives on the locked animation; bookings carry a stable UUID. */
final class OpenFabLab_Slots {
    public static function enabled($animation) { return ($animation['booking_mode'] ?? 'whole') === 'slots'; }
    public static function catalogue($animation) {
        $rows = json_decode($animation['slots_json'] ?? '[]', true);
        if (!is_array($rows)) { throw new RuntimeException('Catalogue de créneaux invalide.'); }
        return $rows;
    }
    public static function context($animation, $uuid = null) {
        if (!self::enabled($animation)) {
            if ($uuid) { throw new RuntimeException('Cette animation ne se réserve pas par créneau.'); }
            return $animation;
        }
        if (!is_string($uuid) || !preg_match('/^[a-f0-9-]{36}$/D', $uuid)) { throw new RuntimeException('Choisissez un créneau valide.'); }
        foreach (self::catalogue($animation) as $slot) {
            if ($slot['slot_uuid'] === $uuid) {
                return array_merge($animation, ['starts_at'=>$slot['starts_at'], 'ends_at'=>$slot['ends_at'],
                    'capacity'=>(int)$slot['capacity'], 'slot_uuid'=>$uuid]);
            }
        }
        throw new RuntimeException('Ce créneau ne fait pas partie de cette animation.');
    }
    public static function scope($animation, $uuid, $alias = '') {
        if (!self::enabled($animation)) { return ''; }
        self::context($animation, $uuid);
        global $wpdb;
        return $wpdb->prepare(' AND ' . $alias . 'slot_uuid = %s', $uuid);
    }
    public static function used($animation, $uuid = null) {
        if (OpenFabLab_Bookings::historical_engine_disabled()) { throw new RuntimeException('La capacité est calculée uniquement par OpenFabLab.'); }
        global $wpdb;
        $table = OpenFabLab_Database::table('reservations');
        $used = $wpdb->get_var($wpdb->prepare(
            "SELECT COUNT(*) FROM $table WHERE animation_id = %d AND status IN ('confirmed','offer_pending','present','absent')"
            . self::scope($animation, $uuid), $animation['id']));
        if ($used === null || !empty($wpdb->last_error)) { throw new RuntimeException('Disponibilité momentanément indisponible.'); }
        return (int)$used;
    }
    public static function configuration($payload, $start, $end) {
        $mode = $payload['booking_mode'] ?? 'whole';
        if (!in_array($mode, ['whole','slots'], true)) { throw new RuntimeException('Mode de réservation invalide.'); }
        $data = ['booking_mode'=>$mode, 'slot_duration_minutes'=>20, 'slot_gap_minutes'=>0, 'slot_capacity'=>1, 'slots_json'=>'[]'];
        if ($mode === 'whole') { return $data; }
        foreach (['slot_duration_minutes'=>[1,480], 'slot_gap_minutes'=>[0,480], 'slot_capacity'=>[1,100000]] as $key=>$range) {
            $value = $payload[$key] ?? null;
            if ((!is_int($value) && !is_string($value)) || filter_var($value, FILTER_VALIDATE_INT) === false
                || (int)$value<$range[0] || (int)$value>$range[1]) { throw new RuntimeException('Paramètre de créneau invalide.'); }
            $data[$key]=(int)$value;
        }
        $slots = $payload['slots'] ?? null;
        if (!is_array($slots) || !$slots || count($slots)>1440) { throw new RuntimeException('Au moins un créneau valide est requis.'); }
        $next=$start->getTimestamp(); $finish=$end->getTimestamp(); $duration=$data['slot_duration_minutes']*60;
        $normalized=[]; $ids=[];
        foreach ($slots as $slot) {
            if (!is_array($slot) || !is_string($slot['slot_uuid'] ?? null)
                || !preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/D',$slot['slot_uuid'])
                || isset($ids[$slot['slot_uuid']])) { throw new RuntimeException('Identifiant de créneau invalide.'); }
            $a = new DateTimeImmutable($slot['starts_at'], new DateTimeZone('UTC'));
            $b = new DateTimeImmutable($slot['ends_at'], new DateTimeZone('UTC'));
            if ($a->getTimestamp()!==$next || $b->getTimestamp()!==$next+$duration || $b->getTimestamp()>$finish
                || (int)($slot['capacity'] ?? 0)!==$data['slot_capacity']) { throw new RuntimeException('Horaires de créneau incohérents.'); }
            $ids[$slot['slot_uuid']]=true;
            $normalized[]=['slot_uuid'=>$slot['slot_uuid'], 'starts_at'=>$a->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s'),
                'ends_at'=>$b->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s'), 'capacity'=>$data['slot_capacity']];
            $next += $duration+$data['slot_gap_minutes']*60;
        }
        if ($next+$duration<=$finish || (int)$payload['capacity']!==count($slots)*$data['slot_capacity']) {
            throw new RuntimeException('Catalogue incomplet ou capacité totale incohérente.');
        }
        $data['slots_json']=wp_json_encode($normalized);
        return $data;
    }
    public static function protect_update($old, $data) {
        if (!$old) { return; }
        global $wpdb;
        $table=OpenFabLab_Database::table('reservations');
        $exists=$wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $table WHERE animation_id = %d", $old['id']));
        if ($exists === null || !empty($wpdb->last_error)) { throw new RuntimeException('Vérification des inscriptions indisponible.'); }
        if (!$exists) { return; }
        $changed=false;
        foreach (['starts_at','ends_at','timezone','booking_mode','slot_duration_minutes','slot_gap_minutes'] as $key) {
            if ((string)($old[$key] ?? ($key==='booking_mode'?'whole':$data[$key])) !== (string)$data[$key]) { $changed=true; }
        }
        if (self::enabled($old)) {
            $a=array_map(fn($s)=>[$s['slot_uuid'],$s['starts_at'],$s['ends_at']],self::catalogue($old));
            $b=array_map(fn($s)=>[$s['slot_uuid'],$s['starts_at'],$s['ends_at']],self::catalogue($data));
            $changed=$changed || $a!==$b || (int)$data['slot_capacity']<(int)$old['slot_capacity'];
        } else { $changed=$changed || (int)$data['capacity']<(int)$old['capacity']; }
        if ($changed) { throw new RuntimeException('Des inscriptions existent : horaires, mode et réduction de capacité protégés.'); }
    }
    public static function time_label($animation) {
        $zone=new DateTimeZone($animation['timezone']);
        $a=(new DateTimeImmutable($animation['starts_at'],new DateTimeZone('UTC')))->setTimezone($zone);
        $b=(new DateTimeImmutable($animation['ends_at'],new DateTimeZone('UTC')))->setTimezone($zone);
        return $a->format('d/m/Y H:i') . '–' . $b->format('H:i');
    }
}
