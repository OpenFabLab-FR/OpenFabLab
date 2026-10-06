<?php
if (!defined('ABSPATH')) { exit; }

final class OpenFabLab_API {
    public static function register() {
        OpenFabLab_Relay::register();
        $private = [
            '/sync/capabilities' => 'capabilities',
            '/sync/snapshot' => 'snapshot',
            '/sync/animations' => 'legacy_disabled',
            '/sync/directory' => 'legacy_disabled',
            '/sync/events' => 'legacy_disabled',
            '/sync/commands' => 'legacy_disabled',
            '/heartbeat' => 'legacy_disabled',
        ];
        foreach ($private as $route => $method) {
            register_rest_route('openfablab/v1', $route, [
                'methods' => 'POST', 'callback' => [__CLASS__, $method],
                'permission_callback' => [__CLASS__, 'private_permission'],
            ]);
        }
        register_rest_route('openfablab/v1', '/public/animations', [
            'methods' => 'GET', 'callback' => [__CLASS__, 'public_animations'],
            'permission_callback' => '__return_true',
        ]);
        foreach (['/public/verify' => 'public_verify', '/public/contact' => 'public_contact', '/public/reserve' => 'public_reserve'] as $route => $method) {
            register_rest_route('openfablab/v1', $route, [
                'methods' => 'POST', 'callback' => [__CLASS__, $method],
                'permission_callback' => [__CLASS__, 'public_permission'],
            ]);
        }
    }

    private static function body(WP_REST_Request $request) {
        $value = json_decode($request->get_body(), true);
        return is_array($value) ? $value : [];
    }

    public static function capabilities(WP_REST_Request $request) {
        return ['ok' => true, 'animation_slots_v1' => true, 'catalog_snapshot_v1' => false,
                'custom_categories_v1' => true, 'protocol_version' => 4, 'family_gateway_v1' => false,
                'outbound_actions_v1' => true,
                'plugin_version' => defined('OPENFABLAB_RES_VERSION') ? OPENFABLAB_RES_VERSION : '2.7.0'];
    }

    public static function legacy_disabled(WP_REST_Request $request) {
        return new WP_Error('openfablab_legacy_disabled', 'Ce parcours historique est désactivé. OpenFabLab traite les demandes du relais.', ['status' => 409]);
    }

    public static function snapshot(WP_REST_Request $request) {
        return self::legacy_disabled($request);
    }

    public static function private_permission(WP_REST_Request $request) {
        $secret = (string) get_option('openfablab_res_sync_secret', '');
        $timestamp = $request->get_header('x-openfablab-timestamp');
        $nonce = $request->get_header('x-openfablab-nonce');
        $signature = $request->get_header('x-openfablab-signature');
        if (!$secret || !is_ssl() || !ctype_digit((string) $timestamp)
            || abs(time() - (int) $timestamp) > 300
            || !preg_match('/^[A-Za-z0-9_-]{20,80}$/D', (string) $nonce)
            || !preg_match('/^[a-f0-9]{64}$/D', (string) $signature)) {
            return new WP_Error('openfablab_forbidden', 'Synchronisation refusée.', ['status' => 403]);
        }
        $canonical = $timestamp . "\n" . $nonce . "\n" . $request->get_method()
            . "\n" . $request->get_route() . "\n" . hash('sha256', $request->get_body());
        $expected = hash_hmac('sha256', $canonical, $secret);
        if (!hash_equals($expected, $signature)) {
            return new WP_Error('openfablab_forbidden', 'Synchronisation refusée.', ['status' => 403]);
        }
        OpenFabLab_Relay::authenticated($request,$nonce);
        global $wpdb;
        $nonces = OpenFabLab_Database::table('nonces');
        $replay_hash = hash_hmac('sha256', $nonce, $secret);
        $inserted = $wpdb->query($wpdb->prepare(
            "INSERT IGNORE INTO $nonces (nonce_hash, expires_at) VALUES (%s, %s)",
            $replay_hash, gmdate('Y-m-d H:i:s', time() + 600)
        ));
        if ($inserted !== 1) {
            return new WP_Error('openfablab_replay', 'Requête déjà traitée.', ['status' => 409]);
        }
        update_option('openfablab_res_last_sync', gmdate('d/m/Y H:i') . ' UTC', false);
        $body = self::body($request);
        if (in_array($body['environment'] ?? '', ['test','production'], true)) {
            update_option('openfablab_res_attempt_' . $body['environment'], gmdate('c'), false);
        }
        return true;
    }

    public static function public_permission(WP_REST_Request $request) {
        return OpenFabLab_Relay::permission($request);
    }

    public static function sync_directory(WP_REST_Request $request) {
        if (OpenFabLab_Bookings::historical_engine_disabled()) { return self::legacy_disabled($request); }
        global $wpdb;
        $body = self::body($request);
        $environment = $body['environment'] ?? '';
        $users = $body['users'] ?? null;
        if (!in_array($environment, ['test', 'production'], true) || !is_array($users) || count($users) > 10000) {
            return new WP_Error('bad_directory', 'Annuaire invalide.', ['status' => 400]);
        }
        $table = OpenFabLab_Database::table('directory');
        $wpdb->query('START TRANSACTION');
        try {
            $wpdb->delete($table, ['environment' => $environment]);
            foreach ($users as $user) {
                if (!is_array($user) || !preg_match('/^[0-9]{4}$/D', (string) ($user['public_id'] ?? ''))
                    || !preg_match('/^[a-z0-9_-]{1,40}$/D', (string) ($user['category'] ?? ''))) {
                    throw new RuntimeException('Annuaire invalide.');
                }
                foreach (['email_hmac', 'phone_hmac'] as $field) {
                    if (!empty($user[$field]) && !preg_match('/^[a-f0-9]{64}$/D', (string) $user[$field])) {
                        throw new RuntimeException('Empreinte de contact invalide.');
                    }
                }
                // Older senders remain compatible; only the signed private endpoint
                // can populate the additional prefill data. Never echo this payload.
                $private = [];
                foreach (['first_name' => 80, 'last_name' => 80, 'email' => 254, 'phone' => 40] as $field => $maximum) {
                    $value = $user[$field] ?? '';
                    if (!is_string($value) || strlen($value) > $maximum) {
                        throw new RuntimeException('Annuaire invalide.');
                    }
                    $private[$field] = $field === 'email' ? sanitize_email($value) : sanitize_text_field($value);
                }
                $ok = $wpdb->insert($table, [
                    'environment' => $environment, 'public_id' => $user['public_id'],
                    'active' => !empty($user['active']) ? 1 : 0,
                    'birth_year' => isset($user['birth_year']) ? (int) $user['birth_year'] : null,
                    'category' => $user['category'],
                    'first_name' => $private['first_name'], 'last_name' => $private['last_name'],
                    'email' => $private['email'], 'phone' => $private['phone'],
                    'email_hmac' => (string) ($user['email_hmac'] ?? ''),
                    'phone_hmac' => (string) ($user['phone_hmac'] ?? ''),
                    'updated_at' => gmdate('Y-m-d H:i:s'),
                ]);
                if (!$ok) { throw new RuntimeException('Annuaire non enregistré.'); }
            }
            $wpdb->query('COMMIT');
            return ['ok' => true, 'count' => count($users)];
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            return new WP_Error('directory_failed', 'Annuaire non enregistré.', ['status' => 500]);
        }
    }

    public static function sync_animations(WP_REST_Request $request, $in_transaction = false) {
        if (OpenFabLab_Bookings::historical_engine_disabled()) { return self::legacy_disabled($request); }
        global $wpdb;
        $body = self::body($request);
        $environment = $body['environment'] ?? '';
        $service_id = (int) ($body['service_id'] ?? 0);
        if (!in_array($environment, ['test', 'production'], true) || $service_id <= 0) {
            return new WP_Error('bad_animation', 'Animation invalide.', ['status' => 400]);
        }
        $table = OpenFabLab_Database::table('animations');
        if (($body['command'] ?? '') === 'delete') {
            $ok = $wpdb->update($table, ['published' => 0, 'updated_at' => gmdate('Y-m-d H:i:s')],
                          ['environment' => $environment, 'service_id' => $service_id]);
            if ($ok === false) { return new WP_Error('delete_failed', 'Dépublication refusée.', ['status'=>500]); }
            return ['ok' => true];
        }
        $animation = $body['animation'] ?? null;
        if (!is_array($animation) || $animation['environment'] !== $environment
            || (int) $animation['service_id'] !== $service_id) {
            return new WP_Error('bad_animation', 'Animation invalide.', ['status' => 400]);
        }
        try {
            $zone = new DateTimeZone($animation['timezone'] ?? 'Europe/Paris');
            $start = new DateTimeImmutable($animation['service_date'] . ' ' . $animation['start_time'], $zone);
            $end = new DateTimeImmutable($animation['service_date'] . ' ' . $animation['end_time'], $zone);
            if ($end <= $start || (int) $animation['capacity'] < 0
                || !in_array($animation['audience'], ['all', 'registered'], true)) {
                throw new InvalidArgumentException();
            }
            $open_at = null;
            if (!empty($animation['signup_open_at'])) {
                $open_at = (new DateTimeImmutable($animation['signup_open_at']))->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s');
            }
            $data = [
                'environment' => $environment, 'service_id' => $service_id,
                'title' => sanitize_text_field($animation['title']),
                'description' => wp_kses_post($animation['description']),
                'starts_at' => $start->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s'),
                'ends_at' => $end->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s'),
                'timezone' => $zone->getName(), 'capacity' => (int) $animation['capacity'],
                'minimum_age' => (int) $animation['minimum_age'],
                'audience' => $animation['audience'],
                'accompaniment_under_age' => (int) $animation['accompaniment_under_age'],
                'waitlist_enabled' => !empty($animation['waitlist_enabled']) ? 1 : 0,
                'close_minutes' => (int) $animation['close_minutes'],
                'signup_open_at' => $open_at,
                'reminder_one_hours' => $animation['reminder_one_hours'],
                'reminder_two_hours' => $animation['reminder_two_hours'],
                'offer_hours' => (int) ($animation['offer_hours'] ?? 12),
                'last_offer_hours' => (int) ($animation['last_offer_hours'] ?? 24),
                'published' => !empty($animation['published']) ? 1 : 0,
                'updated_at' => gmdate('Y-m-d H:i:s'),
            ];
            $data += OpenFabLab_Slots::configuration($animation, $start, $end);
        } catch (Throwable $error) {
            return new WP_Error('bad_animation', 'Date ou paramètre invalide.', ['status' => 400]);
        }
        if (!$in_transaction) { $wpdb->query('START TRANSACTION'); }
        try {
            $existing = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM $table WHERE environment = %s AND service_id = %d FOR UPDATE", $environment, $service_id
            ), ARRAY_A);
            OpenFabLab_Slots::protect_update($existing, $data);
            $ok = $existing ? $wpdb->update($table, $data, ['id' => $existing['id']]) : $wpdb->insert($table, $data);
            if ($ok === false) { throw new RuntimeException('Publication impossible.'); }
            if (!$in_transaction && $wpdb->query('COMMIT') === false) { throw new RuntimeException('Publication impossible.'); }
        } catch (Throwable $error) {
            if (!$in_transaction) { $wpdb->query('ROLLBACK'); }
            return new WP_Error('save_failed', $error->getMessage(), ['status' => 409]);
        }
        if (array_key_exists('privacy_policy_url', $animation)) {
            $privacy_url = esc_url_raw((string) $animation['privacy_policy_url']);
            if ($privacy_url === '' || str_starts_with($privacy_url, 'https://')) {
                update_option('openfablab_res_privacy_url', $privacy_url, false);
            }
        }
        return ['ok' => true];
    }

    public static function sync_events(WP_REST_Request $request) {
        if (OpenFabLab_Bookings::historical_engine_disabled()) { return self::legacy_disabled($request); }
        global $wpdb;
        $body = self::body($request);
        $environment = $body['environment'] ?? '';
        if (!in_array($environment, ['test', 'production'], true)) {
            return new WP_Error('bad_environment', 'Environnement inconnu.', ['status' => 400]);
        }
        $cursor = max(0, (int) ($body['cursor'] ?? 0));
        $limit = min(100, max(1, (int) ($body['limit'] ?? 100)));
        $events = OpenFabLab_Database::table('events');
        $bookings = OpenFabLab_Database::table('reservations');
        $rows = $wpdb->get_results($wpdb->prepare(
            "SELECT e.id AS event_id, e.event_type, r.* FROM $events e "
            . "JOIN $bookings r ON r.uuid = e.reservation_uuid "
            . "WHERE e.environment = %s AND e.id > %d ORDER BY e.id LIMIT %d",
            $environment, $cursor, $limit
        ), ARRAY_A);
        $result = [];
        foreach ($rows as $row) {
            // Advance even when a historical event cannot be represented locally.
            // Otherwise a skipped row can be replayed forever at the page boundary.
            $cursor = (int) $row['event_id'];
            $animation = $wpdb->get_row($wpdb->prepare(
                'SELECT service_id FROM ' . OpenFabLab_Database::table('animations') . ' WHERE id = %d',
                $row['animation_id']
            ), ARRAY_A);
            if (!$animation) { continue; }
            $result[] = ['id' => (int) $row['event_id'], 'type' => $row['event_type'],
                         'booking' => [
                'uuid' => $row['uuid'], 'service_id' => (int) $animation['service_id'],
                'environment' => $row['environment'], 'first_name' => $row['first_name'],
                'last_name' => $row['last_name'], 'birth_year' => (int) $row['birth_year'],
                'email' => $row['email'], 'phone' => $row['phone'], 'status' => $row['status'],
                'link_status' => $row['link_status'], 'public_id' => $row['public_id'],
                'group_uuid' => $row['group_uuid'], 'source' => $row['source'],
                'slot_uuid' => $row['slot_uuid'] ?? null,
                'is_present' => $row['is_present'],
                'created_at' => str_replace(' ', 'T', $row['created_at']) . '+00:00',
                'updated_at' => str_replace(' ', 'T', $row['updated_at']) . '+00:00',
            ]];
        }
        if (!empty($wpdb->last_error)) {
            update_option('openfablab_res_error_' . $environment, 'Lecture du flux refusée.', false);
            return new WP_Error('events_failed', 'Flux indisponible.', ['status'=>500]);
        }
        $has_more = count($rows) === $limit;
        if (!$has_more) {
            update_option('openfablab_res_success_' . $environment, gmdate('c'), false);
            update_option('openfablab_res_error_' . $environment, '', false);
        }
        $response = new WP_REST_Response(['ok'=>true, 'events' => $result, 'cursor' => (string) $cursor, 'has_more'=>$has_more]);
        $response->header('Cache-Control', 'private, no-store');
        return $response;
    }

    public static function sync_commands(WP_REST_Request $request) {
        if (OpenFabLab_Bookings::historical_engine_disabled()) { return self::legacy_disabled($request); }
        global $wpdb;
        $body = self::body($request);
        $uuid = (string) ($body['uuid'] ?? '');
        $action = (string) ($body['action'] ?? '');
        if (!preg_match('/^[a-f0-9-]{36}$/D', $uuid)
            || !in_array($action, ['present', 'absent', 'cancel', 'confirm', 'verify', 'link', 'unlink', 'walkin'], true)) {
            return new WP_Error('bad_command', 'Action inconnue.', ['status' => 400]);
        }
        $table = OpenFabLab_Database::table('reservations');
        if ($action === 'walkin') {
            $environment = $body['environment'] ?? '';
            $service_id = (int) ($body['service_id'] ?? 0);
            $first = sanitize_text_field((string) ($body['first_name'] ?? ''));
            $last = sanitize_text_field((string) ($body['last_name'] ?? ''));
            $year = (int) ($body['birth_year'] ?? 0);
            if (!in_array($environment, ['test', 'production'], true) || !$first || !$last
                || $year < 1900 || $year > (int) gmdate('Y') || $service_id <= 0) {
                return new WP_Error('bad_walkin', 'Participant invalide.', ['status' => 400]);
            }
            $animations = OpenFabLab_Database::table('animations');
            $wpdb->query('START TRANSACTION');
            try {
                $animation = $wpdb->get_row($wpdb->prepare(
                    "SELECT * FROM $animations WHERE environment = %s AND service_id = %d FOR UPDATE",
                    $environment, $service_id
                ), ARRAY_A);
                if (!$animation) { throw new RuntimeException('Animation introuvable.'); }
                $animation = OpenFabLab_Slots::context($animation, $body['slot_uuid'] ?? null);
                $existing = $wpdb->get_var($wpdb->prepare("SELECT id FROM $table WHERE uuid = %s", $uuid));
                if ($existing) { $wpdb->query('COMMIT'); return ['ok' => true]; }
                $used = OpenFabLab_Slots::used($animation, $animation['slot_uuid'] ?? null);
                if ($used >= (int) $animation['capacity'] && empty($body['capacity_override'])) {
                    throw new RuntimeException('Capacité atteinte.');
                }
                $public_id = (string) ($body['public_id'] ?? '');
                if ($public_id && !preg_match('/^[0-9]{4}$/D', $public_id)) {
                    throw new RuntimeException('Identifiant invalide.');
                }
                $saved = $wpdb->insert($table, [
                    'uuid' => $uuid, 'environment' => $environment,
                    'slot_uuid' => $animation['slot_uuid'] ?? null,
                    'animation_id' => $animation['id'], 'first_name' => $first, 'last_name' => $last,
                    'birth_year' => $year,
                    'email' => sanitize_email((string) ($body['email'] ?? '')),
                    'phone' => sanitize_text_field((string) ($body['phone'] ?? '')),
                    'status' => 'confirmed', 'link_status' => $public_id ? 'manual' : 'visitor',
                    'public_id' => $public_id ?: null,
                    'identity_key' => hash_hmac('sha256', 'walkin|' . $uuid,
                        (string) get_option('openfablab_res_sync_secret', '')),
                    'is_present' => 1, 'source' => 'walkin',
                    'created_at' => gmdate('Y-m-d H:i:s'), 'updated_at' => gmdate('Y-m-d H:i:s'),
                ]);
                if (!$saved) { throw new RuntimeException('Participant non enregistré.'); }
                OpenFabLab_Database::event($environment, 'admin_walkin', $uuid);
                $wpdb->query('COMMIT');
                return ['ok' => true];
            } catch (Throwable $error) {
                $wpdb->query('ROLLBACK');
                return new WP_Error('walkin_failed', $error->getMessage(), ['status' => 409]);
            }
        }
        $booking = $wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE uuid = %s", $uuid), ARRAY_A);
        if (!$booking || $booking['environment'] !== ($body['environment'] ?? null)) {
            return new WP_Error('not_found', 'Réservation inconnue.', ['status' => 404]);
        }
        if ($action === 'confirm') {
            return self::confirm_booking($booking, !empty($body['capacity_override']));
        }
        if ($action === 'cancel') {
            $animations = OpenFabLab_Database::table('animations');
            $wpdb->query('START TRANSACTION');
            try {
                $animation = $wpdb->get_row($wpdb->prepare(
                    "SELECT * FROM $animations WHERE id = %d FOR UPDATE", $booking['animation_id']
                ), ARRAY_A);
                if (!$animation) { throw new RuntimeException('Animation introuvable.'); }
                $group = $booking['group_uuid'];
                $members = $wpdb->get_results($wpdb->prepare(
                    $group ? "SELECT uuid, status FROM $table WHERE animation_id = %d AND group_uuid = %s"
                           : "SELECT uuid, status FROM $table WHERE animation_id = %d AND uuid = %s",
                    $animation['id'], $group ?: $uuid
                ), ARRAY_A);
                $changed = false;
                foreach ($members as $member) {
                    if (in_array($member['status'], ['cancelled', 'expired'], true)) { continue; }
                    $ok = $wpdb->update($table, ['status' => 'cancelled', 'is_present' => 0,
                        'updated_at' => gmdate('Y-m-d H:i:s')], ['uuid' => $member['uuid']]);
                    if ($ok === false) { throw new RuntimeException('Annulation impossible.'); }
                    OpenFabLab_Database::event($booking['environment'], 'admin_cancel', $member['uuid']);
                    $changed = true;
                }
                $wpdb->query('COMMIT');
            } catch (Throwable $error) {
                $wpdb->query('ROLLBACK');
                return new WP_Error('save_failed', 'Annulation impossible.', ['status' => 500]);
            }
            if ($changed) { OpenFabLab_Bookings::promote_waitlist((int) $booking['animation_id'], $booking['slot_uuid'] ?? null); }
            return ['ok' => true];
        }
        if (in_array($action, ['present', 'absent'], true)) {
            $animations = OpenFabLab_Database::table('animations');
            $wpdb->query('START TRANSACTION');
            try {
                $animation = $wpdb->get_row($wpdb->prepare(
                    "SELECT * FROM $animations WHERE id = %d FOR UPDATE", $booking['animation_id']
                ), ARRAY_A);
                // Read again under the capacity lock: a concurrent cancellation wins.
                $current = $wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE uuid = %s", $uuid), ARRAY_A);
                if (!$animation || !$current || !in_array($current['status'], ['confirmed', 'present', 'absent'], true)) {
                    throw new RuntimeException('Réservation non confirmée.');
                }
                $presence = $action === 'present' ? 1 : 0;
                if ($current['status'] !== 'confirmed' || $current['is_present'] === null
                    || (int) $current['is_present'] !== $presence) {
                    if ($wpdb->update($table, ['status' => 'confirmed', 'is_present' => $presence,
                        'updated_at' => gmdate('Y-m-d H:i:s')], ['uuid' => $uuid]) === false) {
                        throw new RuntimeException('Modification impossible.');
                    }
                    OpenFabLab_Database::event($booking['environment'], 'admin_' . $action, $uuid);
                }
                $wpdb->query('COMMIT');
                return ['ok' => true];
            } catch (Throwable $error) {
                $wpdb->query('ROLLBACK');
                return new WP_Error('invalid_status', 'Présence impossible : inscription non confirmée ou modification refusée.', ['status' => 409]);
            }
        }
        $changes = ['updated_at' => gmdate('Y-m-d H:i:s')];
        if ($action === 'verify') { $changes['link_status'] = 'manual'; }
        if ($action === 'link') {
            $public_id = (string) ($body['public_id'] ?? '');
            if (!preg_match('/^[0-9]{4}$/D', $public_id)) { return new WP_Error('bad_user', 'Identifiant invalide.', ['status' => 400]); }
            $changes['public_id'] = $public_id; $changes['link_status'] = 'manual';
        }
        if ($action === 'unlink') { $changes['public_id'] = null; $changes['link_status'] = 'visitor'; }
        $same = true;
        foreach ($changes as $field => $value) {
            if ($field !== 'updated_at' && (string) ($booking[$field] ?? '') !== (string) ($value ?? '')) {
                $same = false;
            }
        }
        if ($same) { return ['ok' => true]; }
        if ($wpdb->update($table, $changes, ['uuid' => $uuid]) === false) {
            return new WP_Error('save_failed', 'Modification impossible.', ['status' => 500]);
        }
        OpenFabLab_Database::event($booking['environment'], 'admin_' . $action, $uuid);
        return ['ok' => true];
    }

    private static function confirm_booking($booking, $capacity_override) {
        global $wpdb;
        $table = OpenFabLab_Database::table('reservations');
        $animations = OpenFabLab_Database::table('animations');
        $wpdb->query('START TRANSACTION');
        try {
            // All capacity-changing operations lock the same animation row.
            $animation = $wpdb->get_row($wpdb->prepare(
                "SELECT * FROM $animations WHERE id = %d FOR UPDATE", $booking['animation_id']
            ), ARRAY_A);
            if (!$animation) { throw new RuntimeException('Animation introuvable.'); }
            $animation = OpenFabLab_Slots::context($animation, $booking['slot_uuid'] ?? null);
            $members = $wpdb->get_results($wpdb->prepare(
                $booking['group_uuid']
                    ? "SELECT * FROM $table WHERE animation_id = %d AND group_uuid = %s"
                    : "SELECT * FROM $table WHERE animation_id = %d AND uuid = %s",
                $animation['id'], $booking['group_uuid'] ?: $booking['uuid']
            ), ARRAY_A);
            $all_confirmed = count($members) > 0;
            $incompatible = !count($members);
            $additional = 0;
            foreach ($members as $member) {
                if (($member['slot_uuid'] ?? null) !== ($booking['slot_uuid'] ?? null)) {
                    throw new RuntimeException('Groupe de réservation incohérent.');
                }
                $reserved = in_array($member['status'], ['confirmed', 'present', 'absent'], true);
                $all_confirmed = $all_confirmed && $reserved;
                $incompatible = $incompatible || !in_array($member['status'],
                    ['waitlisted', 'offer_pending', 'confirmed', 'present', 'absent'], true);
                if ($member['status'] === 'waitlisted') { ++$additional; }
            }
            if ($all_confirmed) { $wpdb->query('COMMIT'); return ['ok' => true]; }
            $used = OpenFabLab_Slots::used($animation, $booking['slot_uuid'] ?? null);
            $reason = $incompatible ? 'state' : (($used + $additional > (int) $animation['capacity']
                && !$capacity_override) ? 'capacity' : '');
            if ($reason) {
                $wpdb->query('ROLLBACK');
                foreach ($members as $member) {
                    OpenFabLab_Database::event($booking['environment'], 'admin_confirmation_refused', $member['uuid']);
                }
                return ['ok' => true, 'confirmation' => 'refused', 'reason' => $reason];
            }
            $changed = [];
            foreach ($members as $member) {
                if (in_array($member['status'], ['confirmed', 'present', 'absent'], true)) { continue; }
                if ($wpdb->update($table, ['status' => 'confirmed', 'offer_expires_at' => null,
                    'updated_at' => gmdate('Y-m-d H:i:s')], ['uuid' => $member['uuid']]) === false) {
                    throw new RuntimeException('Confirmation impossible.');
                }
                $wpdb->update(OpenFabLab_Database::table('tokens'), ['used_at' => gmdate('Y-m-d H:i:s')],
                              ['reservation_uuid' => $member['uuid'], 'token_type' => 'offer']);
                OpenFabLab_Database::event($booking['environment'], 'admin_confirmed', $member['uuid']);
                $changed[] = $member['uuid'];
            }
            $wpdb->query('COMMIT');
            foreach ($changed as $uuid) { OpenFabLab_Bookings::send_confirmation($uuid, $animation); }
            return ['ok' => true];
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            return new WP_Error('confirmation_failed', 'Confirmation impossible.', ['status' => 500]);
        }
    }

    public static function heartbeat(WP_REST_Request $request) {
        if (OpenFabLab_Bookings::historical_engine_disabled()) { return self::legacy_disabled($request); }
        OpenFabLab_Bookings::run_due_tasks();
        return ['ok' => true];
    }

    public static function public_animations(WP_REST_Request $request) {
        return OpenFabLab_Family_Gateway::call('catalogue', ['environment' => $request->get_param('environment')]);
    }

    public static function public_verify(WP_REST_Request $request) {
        return OpenFabLab_Family_Gateway::call('identify', self::body($request));
    }

    public static function public_reserve(WP_REST_Request $request) {
        return OpenFabLab_Family_Gateway::call('reserve', self::body($request));
    }

    public static function public_contact(WP_REST_Request $request) {
        return OpenFabLab_Family_Gateway::call('contact', self::body($request));
    }
}
