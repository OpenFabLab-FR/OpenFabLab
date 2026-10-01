<?php
if (!defined('ABSPATH')) { exit; }

final class OpenFabLab_Bookings {
    private static function now() { return current_time('mysql', true); }

    private static function error($code, $message, $status = 400) {
        return new WP_Error($code, $message, ['status' => $status]);
    }

    public static function normalize_phone($phone) {
        $digits = preg_replace('/\D+/', '', (string) $phone);
        if (str_starts_with($digits, '00')) { return '+' . substr($digits, 2); }
        if (str_starts_with($digits, '0') && strlen($digits) === 10) {
            return '+33' . substr($digits, 1);
        }
        return $digits ? '+' . $digits : '';
    }

    private static function fingerprint($kind, $value) {
        $secret = (string) get_option('openfablab_res_sync_secret', '');
        $normalized = $kind === 'email' ? strtolower(trim((string) $value)) : self::normalize_phone($value);
        return $normalized && $secret
            ? hash_hmac('sha256', 'contact/v1|' . $kind . '|' . $normalized, $secret) : '';
    }

    public static function identity($environment, $public_id, $email, $phone) {
        global $wpdb;
        $table = OpenFabLab_Database::table('directory');
        $email_hash = self::fingerprint('email', $email);
        $phone_hash = self::fingerprint('phone', $phone);
        if ($public_id !== '') {
            $row = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM $table WHERE environment = %s AND public_id = %s AND active = 1",
                $environment, $public_id
            ), ARRAY_A);
            if (!$row) { return ['status' => 'unknown', 'public_id' => null]; }
            $email_matches = $email_hash && $row['email_hmac'] && hash_equals($row['email_hmac'], $email_hash);
            $phone_matches = $phone_hash && $row['phone_hmac'] && hash_equals($row['phone_hmac'], $phone_hash);
            // One concordant contact verifies the active public ID; a mismatch
            // on the other contact remains available for a review warning.
            $matched = $email_matches || $phone_matches;
            return ['status' => $matched ? 'matched' : 'needs_review',
                    'public_id' => $public_id,
                    'birth_year' => $matched ? (int) $row['birth_year'] : null,
                    'category' => $matched ? $row['category'] : null,
                    'email_matches' => (bool) $email_matches,
                    'phone_matches' => (bool) $phone_matches];
        }
        if (!$email_hash && !$phone_hash) { return ['status' => 'visitor', 'public_id' => null]; }
        $conditions = [];
        $params = [$environment];
        if ($email_hash) { $conditions[] = 'email_hmac = %s'; $params[] = $email_hash; }
        if ($phone_hash) { $conditions[] = 'phone_hmac = %s'; $params[] = $phone_hash; }
        $rows = $wpdb->get_results($wpdb->prepare(
            "SELECT public_id FROM $table WHERE environment = %s AND active = 1 AND (" . implode(' OR ', $conditions) . ') LIMIT 2',
            ...$params
        ), ARRAY_A);
        return count($rows) === 1
            ? ['status' => 'candidate', 'public_id' => $rows[0]['public_id']]
            : ['status' => 'visitor', 'public_id' => null];
    }

    public static function verify($data) {
        global $wpdb;
        $environment = $data['environment'] ?? '';
        if (!in_array($environment, ['test', 'production'], true)) {
            return self::error('bad_environment', 'Environnement inconnu.');
        }
        $unverified = ['status' => 'unverified',
                       'message' => 'Compte non reconnu. Vérifiez votre identifiant et vos coordonnées.'];
        foreach (['public_id' => 4, 'email' => 254, 'phone' => 40] as $field => $maximum) {
            $value = $data[$field] ?? '';
            if (!is_string($value) || strlen($value) > $maximum) { return $unverified; }
        }
        $public_id = trim($data['public_id'] ?? '');
        if (!preg_match('/^[0-9]{4}$/D', $public_id)) { return $unverified; }
        $result = self::identity($environment, $public_id,
                                 $data['email'] ?? '', $data['phone'] ?? '');
        if ($result['status'] !== 'matched') { return $unverified; }
        $table = OpenFabLab_Database::table('directory');
        $row = $wpdb->get_row($wpdb->prepare(
            "SELECT * FROM $table WHERE environment = %s AND public_id = %s AND active = 1",
            $environment, $public_id
        ), ARRAY_A);
        if (!$row) { return $unverified; }
        $prefill = ['status' => 'matched'];
        foreach (['first_name', 'last_name', 'birth_year', 'email', 'phone'] as $field) {
            $prefill[$field] = $row[$field] ?? '';
        }
        $prefill['masked_identity'] = trim(self::mask_name($prefill['first_name'])
                                          . ' ' . self::mask_name($prefill['last_name']));
        // An invisible, short-lived proof preserves this verification if the
        // participant edits reservation contacts. No code is sent via mail/SMS.
        $expires = time() + 600;
        $nonce = bin2hex(random_bytes(16));
        $canonical = "prefill/v1|$environment|$public_id|$expires|$nonce";
        $prefill['verification_token'] = $expires . '.' . $nonce . '.'
            . hash_hmac('sha256', $canonical, (string) get_option('openfablab_res_sync_secret', ''));
        return $prefill;
    }

    public static function mask_name($name) {
        // Unicode graphemes preserve accents (including combining marks).
        $parts = preg_split('/([\s\p{Pd}]+)/u', trim((string) $name), -1, PREG_SPLIT_DELIM_CAPTURE);
        if ($parts === false) { return ''; }
        return implode('', array_map(function ($part) {
            if (!$part || preg_match('/^[\s\p{Pd}]+$/u', $part)) { return $part; }
            preg_match_all('/\X/u', $part, $letters);
            return ($letters[0][0] ?? '') . str_repeat('*', max(1, count($letters[0]) - 1));
        }, $parts));
    }

    private static function verified_identity($environment, $public_id, $token, $identity) {
        global $wpdb;
        if (!is_string($token) || !preg_match('/^([0-9]{10})\.([a-f0-9]{32})\.([a-f0-9]{64})$/D', $token, $parts)) {
            return $identity;
        }
        $secret = (string) get_option('openfablab_res_sync_secret', '');
        if (!$secret || (int) $parts[1] < time() || (int) $parts[1] > time() + 600
            || !hash_equals(hash_hmac('sha256', "prefill/v1|$environment|$public_id|{$parts[1]}|{$parts[2]}", $secret), $parts[3])) {
            return $identity;
        }
        $table = OpenFabLab_Database::table('directory');
        $row = $wpdb->get_row($wpdb->prepare(
            "SELECT * FROM $table WHERE environment = %s AND public_id = %s AND active = 1",
            $environment, $public_id
        ), ARRAY_A);
        if (!$row) { return $identity; }
        $identity['status'] = 'matched';
        $identity['birth_year'] = (int) $row['birth_year'];
        $identity['category'] = $row['category'];
        return $identity;
    }

    public static function public_animations($environment) {
        global $wpdb;
        if (!in_array($environment, ['test', 'production'], true)) { return []; }
        $table = OpenFabLab_Database::table('animations');
        $bookings = OpenFabLab_Database::table('reservations');
        $rows = $wpdb->get_results($wpdb->prepare(
            "SELECT a.*, COUNT(r.id) AS occupied FROM $table a "
            . "LEFT JOIN $bookings r ON r.animation_id = a.id "
            . "AND r.status IN ('confirmed','offer_pending','present','absent') "
            . "WHERE a.environment = %s AND a.published = 1 AND (CASE WHEN a.booking_mode = 'slots' THEN a.ends_at ELSE a.starts_at END) > %s "
            . "GROUP BY a.id ORDER BY a.starts_at LIMIT 100",
            $environment, self::now()
        ), ARRAY_A);
        $result = [];
        foreach ($rows as $row) {
            $used = (int) $row['occupied'];
            $close = strtotime($row['starts_at'] . ' UTC') - ((int) $row['close_minutes'] * 60);
            $public = [
                'service_id' => (int) $row['service_id'], 'title' => $row['title'],
                'description' => $row['description'], 'starts_at' => $row['starts_at'] . 'Z',
                'ends_at' => $row['ends_at'] . 'Z', 'timezone' => $row['timezone'],
                'capacity' => (int) $row['capacity'], 'available' => max(0, (int) $row['capacity'] - $used),
                'minimum_age' => (int) $row['minimum_age'], 'audience' => $row['audience'],
                'accompaniment_under_age' => (int) $row['accompaniment_under_age'],
                'waitlist_enabled' => (bool) $row['waitlist_enabled'],
                'registration_open' => time() < $close
                    && (!$row['signup_open_at'] || strtotime($row['signup_open_at'] . ' UTC') <= time()),
            ];
            $public['booking_mode'] = $row['booking_mode'] ?? 'whole';
            if (OpenFabLab_Slots::enabled($row)) {
                $public['slots'] = [];
                $public['registration_open'] = false;
                $public['available'] = 0;
                foreach (OpenFabLab_Slots::catalogue($row) as $slot) {
                    $context = OpenFabLab_Slots::context($row, $slot['slot_uuid']);
                    $available = max(0, (int)$slot['capacity'] - OpenFabLab_Slots::used($row, $slot['slot_uuid']));
                    $open = time() < strtotime($slot['starts_at'] . ' UTC') - (int)$row['close_minutes'] * 60
                        && (!$row['signup_open_at'] || strtotime($row['signup_open_at'] . ' UTC') <= time());
                    $public['slots'][] = ['slot_uuid'=>$slot['slot_uuid'], 'starts_at'=>$slot['starts_at'].'Z',
                        'ends_at'=>$slot['ends_at'].'Z', 'capacity'=>(int)$slot['capacity'], 'available'=>$available,
                        'registration_open'=>$open];
                    if ($open) { $public['available'] += $available; }
                    $public['registration_open'] = $public['registration_open'] || $open;
                }
            }
            $result[] = $public;
        }
        return $result;
    }

    private static function identity_key($person, $identity = []) {
        $secret = (string) get_option('openfablab_res_sync_secret', '');
        if (($identity['status'] ?? '') === 'matched' && !empty($identity['public_id'])) {
            return hash_hmac('sha256', 'registered|' . $identity['public_id'], $secret);
        }
        $name = $person['first_name'] . '|' . $person['last_name'];
        $name = function_exists('mb_strtolower') ? mb_strtolower($name) : strtolower($name);
        return hash_hmac('sha256', $name
            . '|' . $person['birth_year'] . '|' . strtolower($person['email'])
            . '|' . self::normalize_phone($person['phone']), $secret);
    }

    private static function validate_person($data) {
        $first = sanitize_text_field((string) ($data['first_name'] ?? ''));
        $last = sanitize_text_field((string) ($data['last_name'] ?? ''));
        $email = sanitize_email((string) ($data['email'] ?? ''));
        $phone = sanitize_text_field((string) ($data['phone'] ?? ''));
        $year = (int) ($data['birth_year'] ?? 0);
        $public_id = trim((string) ($data['public_id'] ?? ''));
        if ($public_id !== '' && !preg_match('/^[0-9]{4}$/D', $public_id)) {
            return self::error('bad_id', 'Identifiant usager invalide.');
        }
        if (!$first || !$last || strlen($first) > 80 || strlen($last) > 80
            || !is_email($email) || strlen($phone) > 40 || strlen(preg_replace('/\D/', '', $phone)) < 8
            || $year < 1900
            || $year > (int) wp_date('Y')) {
            return self::error('invalid_person', 'Complétez le nom, l’année de naissance, l’e-mail et le téléphone.');
        }
        return ['first_name' => $first, 'last_name' => $last, 'email' => $email,
                'phone' => $phone, 'birth_year' => $year,
                'public_id' => $public_id];
    }

    public static function reserve($data) {
        global $wpdb;
        if (!OpenFabLab_Database::tables_are_innodb()) {
            return self::error('storage_unavailable', 'La réservation est momentanément indisponible.', 503);
        }
        if (!empty($data['website'])) { return self::error('spam', 'Demande refusée.'); }
        $environment = $data['environment'] ?? '';
        $service_id = (int) ($data['service_id'] ?? 0);
        if (!in_array($environment, ['test', 'production'], true) || $service_id <= 0) {
            return self::error('invalid_animation', 'Animation introuvable.');
        }
        $main = self::validate_person($data);
        if (is_wp_error($main)) { return $main; }
        $animations = OpenFabLab_Database::table('animations');
        $reservations = OpenFabLab_Database::table('reservations');
        $wpdb->query('START TRANSACTION');
        try {
            $animation = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM $animations WHERE environment = %s AND service_id = %d FOR UPDATE",
                $environment, $service_id
            ), ARRAY_A);
            if (!$animation || !(int) $animation['published']) { throw new RuntimeException('Cette animation n’est pas disponible.'); }
            $animation = OpenFabLab_Slots::context($animation, $data['slot_uuid'] ?? null);
            $scope = OpenFabLab_Slots::scope($animation, $animation['slot_uuid'] ?? null);
            $start = strtotime($animation['starts_at'] . ' UTC');
            $cutoff = $start - (int) $animation['close_minutes'] * 60;
            if (time() >= $cutoff || ($animation['signup_open_at'] && time() < strtotime($animation['signup_open_at'] . ' UTC'))) {
                throw new RuntimeException('Les inscriptions ne sont pas ouvertes.');
            }
            $main_id = self::identity($environment, $main['public_id'], $main['email'], $main['phone']);
            $main_id = self::verified_identity($environment, $main['public_id'],
                                               $data['verification_token'] ?? '', $main_id);
            if ($animation['audience'] === 'registered' && $main_id['status'] === 'unknown') {
                throw new RuntimeException('Un identifiant usager actif est nécessaire pour cette animation.');
            }
            if ($animation['audience'] === 'registered' && !$main['public_id']) {
                throw new RuntimeException('Cette animation est réservée aux usagers inscrits.');
            }
            if ($main_id['status'] === 'matched' && !empty($main_id['birth_year'])) {
                if ($main['birth_year'] >= 1900 && $main['birth_year'] !== $main_id['birth_year']) {
                    $main_id['year_mismatch'] = true;
                } else {
                    $main['birth_year'] = $main_id['birth_year'];
                }
            }
            if ($main['birth_year'] < 1900) {
                throw new RuntimeException('Renseignez l’année de naissance de cette personne.');
            }
            $activity_year = (int) (new DateTimeImmutable($animation['starts_at'], new DateTimeZone('UTC')))
                ->setTimezone(new DateTimeZone($animation['timezone']))->format('Y');
            $age = $activity_year - $main['birth_year'];
            if ($age < (int) $animation['minimum_age']) { throw new RuntimeException('L’âge minimum de l’animation n’est pas atteint.'); }
            $people = [[$main, $main_id]];
            if ($age < (int) $animation['accompaniment_under_age']) {
                $companion_data = $data['companion'] ?? null;
                if (!is_array($companion_data)) { throw new RuntimeException('Un accompagnateur doit aussi réserver une place.'); }
                $companion = self::validate_person($companion_data);
                if (is_wp_error($companion)) { throw new RuntimeException('Complétez les informations de l’accompagnateur.'); }
                if ($activity_year - $companion['birth_year'] < 18) { throw new RuntimeException('L’accompagnateur doit être majeur.'); }
                $companion_id = self::identity($environment, $companion['public_id'], $companion['email'], $companion['phone']);
                // An accompanying adult may be a visitor even for an animation reserved to users.
                $people[] = [$companion, $companion_id];
            }
            foreach ($people as [$person, $identity]) {
                $key = self::identity_key($person, $identity);
                $existing = $wpdb->get_var($wpdb->prepare(
                    "SELECT id FROM $reservations WHERE animation_id = %d AND identity_key = %s AND status IN ('confirmed','waitlisted','offer_pending','present','absent')" . $scope . " LIMIT 1",
                    $animation['id'], $key
                ));
                if ($existing) { throw new RuntimeException('Une réservation existe déjà pour cette personne.'); }
            }
            if (OpenFabLab_Slots::enabled($animation) && count($people) > (int)$animation['capacity']) {
                throw new RuntimeException('Ce créneau ne peut pas accueillir le participant et son accompagnateur.');
            }
            $used = OpenFabLab_Slots::used($animation, $animation['slot_uuid'] ?? null);
            $remaining = (int) $animation['capacity'] - $used;
            $status = $remaining >= count($people) ? 'confirmed' : 'waitlisted';
            if ($status === 'waitlisted' && !(int) $animation['waitlist_enabled']) {
                throw new RuntimeException('Cette animation est complète et la liste d’attente est fermée.');
            }
            $group = count($people) === 2 ? wp_generate_uuid4() : null;
            $created = [];
            foreach ($people as [$person, $identity]) {
                $uuid = wp_generate_uuid4();
                $saved = $wpdb->insert($reservations, [
                    'uuid' => $uuid, 'environment' => $environment, 'animation_id' => $animation['id'],
                    'slot_uuid' => $animation['slot_uuid'] ?? null,
                    'first_name' => $person['first_name'], 'last_name' => $person['last_name'],
                    'birth_year' => $person['birth_year'], 'email' => $person['email'], 'phone' => $person['phone'],
                    'status' => $status,
                    'link_status' => !empty($identity['year_mismatch']) ? 'needs_review' : $identity['status'],
                    'public_id' => $identity['public_id'], 'group_uuid' => $group,
                    'identity_key' => self::identity_key($person, $identity), 'source' => 'online',
                    'created_at' => self::now(), 'updated_at' => self::now(),
                ]);
                if (!$saved) { throw new RuntimeException('La réservation n’a pas pu être enregistrée.'); }
                OpenFabLab_Database::event($environment, 'reservation_' . $status, $uuid);
                $created[] = $uuid;
            }
            $wpdb->query('COMMIT');
            foreach ($created as $uuid) { self::mail_booking($uuid, $animation, $status); }
            return ['status' => $status, 'count' => count($created),
                    'message' => $status === 'confirmed' ? 'Réservation confirmée. Un e-mail vous a été envoyé.'
                    : 'Inscription sur liste d’attente enregistrée. Un e-mail vous a été envoyé.'];
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            return self::error('reservation_refused', $error->getMessage(), 409);
        }
    }

    private static function issue_token($uuid, $type, $expires_at) {
        global $wpdb;
        $token = bin2hex(random_bytes(32));
        $wpdb->insert(OpenFabLab_Database::table('tokens'), [
            'reservation_uuid' => $uuid, 'token_type' => $type,
            'token_hash' => hash('sha256', $token), 'expires_at' => $expires_at,
            'created_at' => self::now(),
        ]);
        return $token;
    }

    private static function mail_booking($uuid, $animation, $status) {
        global $wpdb;
        $row = $wpdb->get_row($wpdb->prepare(
            'SELECT * FROM ' . OpenFabLab_Database::table('reservations') . ' WHERE uuid = %s', $uuid
        ), ARRAY_A);
        if (!$row) { return; }
        $animation = OpenFabLab_Slots::context($animation, $row['slot_uuid'] ?? null);
        $cancel_token = self::issue_token($uuid, 'cancel', $animation['starts_at']);
        $link = add_query_arg(['action' => 'openfablab_cancel', 'booking' => $uuid, 'token' => $cancel_token], admin_url('admin-post.php'));
        self::send_template($status === 'confirmed' ? 'confirmation' : 'waitlist',
                            $row, $animation, ['cancel_url'=>$link]);
    }

    public static function send_confirmation($uuid, $animation) {
        self::mail_booking($uuid, $animation, 'confirmed');
    }

    private static function send_template($kind, $row, $animation, $extra=[]) {
        try {
            $mail=OpenFabLab_Emails::compose($kind,$row,$animation,$extra);
            $sent=OpenFabLab_Emails::deliver($row['email'],$mail['subject'],$mail['body'],$row['environment']);
        } catch (Throwable $error) { $sent=false; }
        if (!$sent) {
            OpenFabLab_Database::event($row['environment'], 'email_failed', $row['uuid']);
        }
    }

    private static function token_row($uuid, $token, $type) {
        global $wpdb;
        if (!preg_match('/^[a-f0-9]{64}$/D', (string) $token)) { return null; }
        $tokens = OpenFabLab_Database::table('tokens');
        return $wpdb->get_row($wpdb->prepare(
            "SELECT * FROM $tokens WHERE reservation_uuid = %s AND token_type = %s AND token_hash = %s AND used_at IS NULL AND expires_at > %s",
            $uuid, $type, hash('sha256', $token), self::now()
        ), ARRAY_A);
    }

    public static function cancel($uuid, $token) {
        global $wpdb;
        $reservations = OpenFabLab_Database::table('reservations');
        $animations = OpenFabLab_Database::table('animations');
        $wpdb->query('START TRANSACTION');
        try {
            $booking = $wpdb->get_row($wpdb->prepare("SELECT * FROM $reservations WHERE uuid = %s", $uuid), ARRAY_A);
            if (!$booking) { throw new RuntimeException('Réservation introuvable.'); }
            $animation = $wpdb->get_row($wpdb->prepare("SELECT * FROM $animations WHERE id = %d FOR UPDATE", $booking['animation_id']), ARRAY_A);
            if ($animation) { $animation = OpenFabLab_Slots::context($animation, $booking['slot_uuid'] ?? null); }
            $booking = $wpdb->get_row($wpdb->prepare("SELECT * FROM $reservations WHERE uuid = %s FOR UPDATE", $uuid), ARRAY_A);
            $token_row = self::token_row($uuid, $token, 'cancel');
            if (!$animation || !$booking || !$token_row || !in_array($booking['status'],['confirmed','waitlisted','offer_pending','present','absent'],true)
                || strtotime($animation['starts_at'] . ' UTC') <= time()) {
                throw new RuntimeException('Ce lien d’annulation n’est plus valable.');
            }
            $group = $booking['group_uuid'];
            $members = $group ? $wpdb->get_results($wpdb->prepare(
                "SELECT * FROM $reservations WHERE group_uuid = %s AND animation_id = %d AND status IN ('confirmed','waitlisted','offer_pending','present','absent')"
                . OpenFabLab_Slots::scope($animation, $booking['slot_uuid'] ?? null) . " FOR UPDATE", $group, $animation['id']
            ), ARRAY_A) : [$booking];
            if (!$members) { throw new RuntimeException('Annulation impossible.'); }
            foreach ($members as $member) {
                if ($wpdb->update($reservations, ['status' => 'cancelled', 'is_present' => 0, 'updated_at' => self::now()],
                              ['uuid' => $member['uuid']]) === false) { throw new RuntimeException('Annulation impossible.'); }
                $tokens=OpenFabLab_Database::table('tokens');
                if ($wpdb->query($wpdb->prepare("UPDATE $tokens SET used_at = %s WHERE reservation_uuid = %s AND used_at IS NULL",
                    self::now(),$member['uuid'])) === false) { throw new RuntimeException('Annulation impossible.'); }
                OpenFabLab_Database::event($booking['environment'], 'reservation_cancelled', $member['uuid']);
            }
            if ($wpdb->query('COMMIT') === false) { throw new RuntimeException('Annulation impossible.'); }
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            return self::error('cancel_refused', $error->getMessage(), 409);
        }
        // One confirmation per distinct recipient, only after a public cancellation commits.
        // Other group tokens/retries cannot send it again; NAS and maintenance never call this path.
        // Keep the existing immediate queue treatment; mail latency must not delay promotion.
        self::promote_waitlist((int)$animation['id'],$booking['slot_uuid']??null);
        $recipients=[];
        foreach ($members as $member) {
            $email=strtolower(sanitize_email($member['email']));
            if (!$email || isset($recipients[$email])) { continue; }
            $recipients[$email]=true;
            self::send_template('cancellation',$member,$animation);
        }
        return true;
    }

    public static function promote_waitlist($animation_id, $slot_uuid = null) {
        global $wpdb;
        $reservations = OpenFabLab_Database::table('reservations');
        $animations = OpenFabLab_Database::table('animations');
        $wpdb->query('START TRANSACTION');
        try {
            $animation = $wpdb->get_row($wpdb->prepare("SELECT * FROM $animations WHERE id = %d FOR UPDATE", $animation_id), ARRAY_A);
            if (!$animation) { $wpdb->query('ROLLBACK'); return false; }
            if (OpenFabLab_Slots::enabled($animation) && !$slot_uuid) {
                // A scheduled sweep visits each independent queue; no nested transaction.
                $wpdb->query('ROLLBACK');
                $changed = false;
                foreach (OpenFabLab_Slots::catalogue($animation) as $slot) {
                    $changed = self::promote_waitlist($animation_id, $slot['slot_uuid']) || $changed;
                }
                return $changed;
            }
            $animation = OpenFabLab_Slots::context($animation, $slot_uuid);
            $scope = OpenFabLab_Slots::scope($animation, $slot_uuid);
            $cutoff = strtotime($animation['starts_at'] . ' UTC') - (int) $animation['close_minutes'] * 60;
            if (time() >= $cutoff) { $wpdb->query('ROLLBACK'); return false; }
            $first = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM $reservations WHERE animation_id = %d AND status = 'waitlisted'" . $scope . " ORDER BY id ASC LIMIT 1",
                $animation_id
            ), ARRAY_A);
            if (!$first) { $wpdb->query('ROLLBACK'); return false; }
            $members = $first['group_uuid'] ? $wpdb->get_results($wpdb->prepare(
                "SELECT * FROM $reservations WHERE group_uuid = %s AND animation_id = %d AND status = 'waitlisted'" . $scope . " ORDER BY id",
                $first['group_uuid'], $animation_id
            ), ARRAY_A) : [$first];
            $used = OpenFabLab_Slots::used($animation, $slot_uuid);
            if ((int) $animation['capacity'] - $used < count($members)) {
                $wpdb->query('ROLLBACK'); return false; // Strict FIFO: never bypass a pair.
            }
            $next = (int) $wpdb->get_var($wpdb->prepare(
                "SELECT COUNT(*) FROM $reservations WHERE animation_id = %d AND status = 'waitlisted' AND id NOT IN ("
                . implode(',', array_map('intval', array_column($members, 'id'))) . ')' . $scope, $animation_id
            ));
            $hours = $next === 0 ? (int) $animation['last_offer_hours'] : (int) $animation['offer_hours'];
            $expires = min($cutoff, time() + max(1, $hours) * HOUR_IN_SECONDS);
            $expiry = gmdate('Y-m-d H:i:s', $expires);
            $offers = [];
            foreach ($members as $member) {
                $wpdb->update($reservations, ['status' => 'offer_pending', 'offer_expires_at' => $expiry,
                                               'updated_at' => self::now()], ['id' => $member['id']]);
                OpenFabLab_Database::event($member['environment'], 'offer_pending', $member['uuid']);
                $offers[] = $member;
            }
            $wpdb->query('COMMIT');
            foreach ($offers as $offer) {
                $token = self::issue_token($offer['uuid'], 'offer', $expiry);
                $link = add_query_arg(['action' => 'openfablab_offer', 'booking' => $offer['uuid'], 'token' => $token], admin_url('admin-post.php'));
                $zone=new DateTimeZone($animation['timezone']);
                $deadline=(new DateTimeImmutable('@'.$expires))->setTimezone($zone)->format('d/m/Y à H:i');
                self::send_template('offer',$offer,$animation,['offer_url'=>$link,'offer_deadline'=>$deadline]);
            }
            return true;
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            return false;
        }
    }

    public static function respond_offer($uuid, $token, $accept) {
        global $wpdb;
        $reservations = OpenFabLab_Database::table('reservations');
        $animations = OpenFabLab_Database::table('animations');
        $wpdb->query('START TRANSACTION');
        try {
            $booking = $wpdb->get_row($wpdb->prepare("SELECT * FROM $reservations WHERE uuid = %s", $uuid), ARRAY_A);
            if (!$booking) { throw new RuntimeException('Offre introuvable.'); }
            $animation = $wpdb->get_row($wpdb->prepare("SELECT * FROM $animations WHERE id = %d FOR UPDATE", $booking['animation_id']), ARRAY_A);
            if ($animation) { $animation = OpenFabLab_Slots::context($animation, $booking['slot_uuid'] ?? null); }
            $booking = $wpdb->get_row($wpdb->prepare("SELECT * FROM $reservations WHERE uuid = %s FOR UPDATE", $uuid), ARRAY_A);
            $token_row = self::token_row($uuid, $token, 'offer');
            if (!$animation || !$booking || !$token_row || $booking['status'] !== 'offer_pending') {
                throw new RuntimeException('Cette offre a expiré ou a déjà été traitée.');
            }
            $members = $booking['group_uuid'] ? $wpdb->get_results($wpdb->prepare(
                "SELECT uuid FROM $reservations WHERE group_uuid = %s AND animation_id = %d AND status = 'offer_pending'"
                . OpenFabLab_Slots::scope($animation, $booking['slot_uuid'] ?? null), $booking['group_uuid'], $animation['id']
            ), ARRAY_A) : [['uuid' => $uuid]];
            $status = $accept ? 'confirmed' : 'cancelled';
            foreach ($members as $member) {
                $wpdb->update($reservations, ['status' => $status, 'offer_expires_at' => null,
                                               'updated_at' => self::now()], ['uuid' => $member['uuid']]);
                OpenFabLab_Database::event($booking['environment'], 'offer_' . ($accept ? 'accepted' : 'refused'), $member['uuid']);
            }
            $wpdb->update(OpenFabLab_Database::table('tokens'), ['used_at' => self::now()], ['id' => $token_row['id']]);
            $wpdb->query('COMMIT');
            if (!$accept) { self::promote_waitlist((int) $animation['id'], $booking['slot_uuid'] ?? null); }
            else { foreach ($members as $member) { self::mail_booking($member['uuid'], $animation, 'confirmed'); } }
            return true;
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            return self::error('offer_refused', $error->getMessage(), 409);
        }
    }

    public static function run_due_tasks() {
        global $wpdb;
        $nonces = OpenFabLab_Database::table('nonces');
        $wpdb->query($wpdb->prepare("DELETE FROM $nonces WHERE expires_at < %s", self::now()));
        $animations = OpenFabLab_Database::table('animations');
        $reservations = OpenFabLab_Database::table('reservations');
        $expired = $wpdb->get_results($wpdb->prepare(
            "SELECT DISTINCT animation_id, slot_uuid FROM $reservations WHERE status = 'offer_pending' AND offer_expires_at <= %s LIMIT 100",
            self::now()
        ), ARRAY_A);
        foreach ($expired as $row) {
            $animation_id = (int) $row['animation_id'];
            $wpdb->query('START TRANSACTION');
            $animation = $wpdb->get_row($wpdb->prepare("SELECT * FROM $animations WHERE id = %d FOR UPDATE", $animation_id), ARRAY_A);
            if ($animation) {
                $scope = OpenFabLab_Slots::scope($animation, $row['slot_uuid'] ?? null);
                $members = $wpdb->get_results($wpdb->prepare(
                    "SELECT uuid, environment FROM $reservations WHERE animation_id = %d AND status = 'offer_pending' AND offer_expires_at <= %s" . $scope,
                    $animation_id, self::now()
                ), ARRAY_A);
                foreach ($members as $member) {
                    $wpdb->update($reservations, ['status' => 'expired', 'updated_at' => self::now()], ['uuid' => $member['uuid']]);
                    OpenFabLab_Database::event($member['environment'], 'offer_expired', $member['uuid']);
                }
            }
            $wpdb->query('COMMIT');
            self::promote_waitlist($animation_id, $row['slot_uuid'] ?? null);
        }
        $upcoming = $wpdb->get_results($wpdb->prepare(
            "SELECT r.*, a.title, a.starts_at, a.reminder_one_hours, a.reminder_two_hours "
            . "FROM $reservations r JOIN $animations a ON a.id = r.animation_id "
            . "WHERE r.status = 'confirmed' AND a.ends_at > %s AND a.starts_at < %s LIMIT 250",
            self::now(), gmdate('Y-m-d H:i:s', time() + 3 * DAY_IN_SECONDS)
        ), ARRAY_A);
        foreach ($upcoming as $row) {
            $animation = $wpdb->get_row($wpdb->prepare("SELECT * FROM $animations WHERE id = %d", $row['animation_id']), ARRAY_A);
            if (!$animation) { continue; }
            $context = OpenFabLab_Slots::context($animation, $row['slot_uuid'] ?? null);
            $row['starts_at'] = $context['starts_at'];
            if (strtotime($row['starts_at'] . ' UTC') <= time()) { continue; }
            foreach ([1, 2] as $number) {
                $hours = (int) $row['reminder_' . ($number === 1 ? 'one' : 'two') . '_hours'];
                $column = $number === 1 ? 'reminder_one_sent_at' : 'reminder_two_sent_at';
                if ($hours <= 0 || $row[$column] || time() < strtotime($row['starts_at'] . ' UTC') - $hours * HOUR_IN_SECONDS) {
                    continue;
                }
                $updated = $wpdb->query($wpdb->prepare(
                    "UPDATE $reservations SET $column = %s WHERE id = %d AND $column IS NULL",
                    self::now(), $row['id']
                ));
                if ($updated === 1) {
                    $token = self::issue_token($row['uuid'], 'cancel', $row['starts_at']);
                    $link = add_query_arg(['action' => 'openfablab_cancel', 'booking' => $row['uuid'], 'token' => $token], admin_url('admin-post.php'));
                    self::send_template($number===1?'reminder_one':'reminder_two',$row,$context,['cancel_url'=>$link]);
                }
            }
        }
        self::purge_old_contacts();
    }

    private static function purge_old_contacts() {
        global $wpdb;
        $table = OpenFabLab_Database::table('reservations');
        $cutoff = gmdate('Y-m-d H:i:s', time() - 2 * YEAR_IN_SECONDS);
        $wpdb->query($wpdb->prepare(
            "UPDATE $table SET email = '', phone = '', first_name = 'Anonyme', last_name = '', public_id = NULL, identity_key = '' "
            . "WHERE updated_at < %s AND email <> ''", $cutoff
        ));
        // A disconnected installation must not keep a stale private directory forever.
        // Fresh snapshots already mirror the contact retention and active-user rules.
        $directory = OpenFabLab_Database::table('directory');
        $wpdb->query($wpdb->prepare("DELETE FROM $directory WHERE updated_at < %s", $cutoff));
    }

    private static function render_action_page($type, $booking = null, $animation = null,
                                               $message = '', $failed = false, $uuid = '', $token = '') {
        nocache_headers();
        header('Referrer-Policy: no-referrer');
        header('X-Robots-Tag: noindex, nofollow', true);
        $title = $type === 'cancel' ? 'Annuler ma réservation' : 'Une place est disponible';
        $logo = plugins_url('assets/OpenFabLab-logo-horizontal.svg', OPENFABLAB_RES_FILE);
        $css = add_query_arg('ver', substr(hash_file('sha256', OPENFABLAB_RES_PATH . 'assets/reservations.css'), 0, 12),
                             plugins_url('assets/reservations.css', OPENFABLAB_RES_FILE));
        echo '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            . '<meta name="viewport" content="width=device-width, initial-scale=1">'
            . '<meta name="referrer" content="no-referrer"><meta name="robots" content="noindex,nofollow">'
            . '<title>' . esc_html($title) . ' · OpenFabLab</title>'
            . '<link rel="stylesheet" href="' . esc_url($css) . '"></head>'
            . '<body class="openfablab-action-body"><main class="openfablab-action-card">'
            . '<img class="openfablab-action-logo" src="' . esc_url($logo) . '" alt="OpenFabLab">'
            . '<h1>' . esc_html($title) . '</h1>';
        if ($booking && $animation) {
            $person = trim($booking['first_name'] . ' ' . $booking['last_name']);
            try {
                $zone = new DateTimeZone($animation['timezone'] ?: 'Europe/Paris');
            } catch (Exception $error) {
                $zone = wp_timezone();
            }
            $date = wp_date('d/m/Y à H:i', strtotime($animation['starts_at'] . ' UTC'), $zone);
            if (OpenFabLab_Slots::enabled($animation)) { $date = OpenFabLab_Slots::time_label($animation); }
            echo '<div class="openfablab-action-summary"><p><strong>Participant :</strong> '
                . esc_html($person) . '</p><p><strong>Animation :</strong> '
                . esc_html($animation['title']) . '</p><p><strong>Date :</strong> '
                . esc_html($date) . '</p></div>';
        }
        if ($message !== '') {
            echo '<p class="openfablab-action-message' . ($failed ? ' is-error' : ' is-success') . '">'
                . esc_html($message) . '</p>';
        } elseif ($booking) {
            echo '<p class="openfablab-action-intro">Confirmez votre choix ci-dessous.</p>';
            echo '<form method="post" class="openfablab-action-form">';
            echo '<input type="hidden" name="action" value="' . esc_attr('openfablab_' . $type) . '">';
            echo '<input type="hidden" name="booking" value="' . esc_attr($uuid) . '">';
            echo '<input type="hidden" name="token" value="' . esc_attr($token) . '">';
            echo wp_nonce_field('openfablab_' . $type . '_' . $uuid, '_wpnonce', false, false);
            if ($type === 'offer') {
                echo '<button class="openfablab-action-button" name="decision" value="accept">Accepter la place</button>'
                    . '<button class="openfablab-action-button is-secondary" name="decision" value="refuse">Refuser</button>';
            } else {
                echo '<button class="openfablab-action-button" type="submit">Confirmer l’annulation</button>';
            }
            echo '</form>';
        }
        echo '</main></body></html>';
    }

    private static function action_page($type) {
        global $wpdb;
        $uuid = sanitize_text_field(wp_unslash($_REQUEST['booking'] ?? ''));
        $token = sanitize_text_field(wp_unslash($_REQUEST['token'] ?? ''));
        if (!$uuid || !$token || !self::token_row($uuid, $token, $type)) {
            status_header(403);
            self::render_action_page($type, null, null, 'Ce lien est invalide ou expiré.', true);
            exit;
        }
        $booking = $wpdb->get_row($wpdb->prepare(
            'SELECT * FROM ' . OpenFabLab_Database::table('reservations') . ' WHERE uuid = %s', $uuid
        ), ARRAY_A);
        $animation = $booking ? $wpdb->get_row($wpdb->prepare(
            'SELECT * FROM ' . OpenFabLab_Database::table('animations') . ' WHERE id = %d', $booking['animation_id']
        ), ARRAY_A) : null;
        if (!$booking || !$animation) {
            status_header(403);
            self::render_action_page($type, null, null, 'Ce lien est invalide ou expiré.', true);
            exit;
        }
        try { $animation = OpenFabLab_Slots::context($animation, $booking['slot_uuid'] ?? null); }
        catch (Throwable $error) {
            status_header(403);
            self::render_action_page($type, null, null, 'Ce lien est invalide ou expiré.', true);
            exit;
        }
        if ($_SERVER['REQUEST_METHOD'] === 'POST') {
            if (!wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'] ?? '')), 'openfablab_' . $type . '_' . $uuid)) {
                status_header(403);
                self::render_action_page($type, null, null, 'Validation invalide.', true);
                exit;
            }
            $result = $type === 'cancel' ? self::cancel($uuid, $token)
                : self::respond_offer($uuid, $token, ($_POST['decision'] ?? '') === 'accept');
            $failed = is_wp_error($result);
            status_header($failed ? 409 : 200);
            $message = $failed ? $result->get_error_message()
                : ($type === 'cancel' ? 'Votre annulation a été enregistrée.' : 'Votre réponse a été enregistrée.');
            self::render_action_page($type, $failed ? null : $booking,
                                     $failed ? null : $animation, $message, $failed);
            exit;
        }
        self::render_action_page($type, $booking, $animation, '', false, $uuid, $token);
        exit;
    }

    public static function cancellation_page() { self::action_page('cancel'); }
    public static function offer_page() { self::action_page('offer'); }
}
