<?php
// Standalone tests: memory-only WordPress stubs, no network or actual mail.
define('ABSPATH', __DIR__);
define('ARRAY_A', 'ARRAY_A');
define('YEAR_IN_SECONDS', 365 * 86400);
define('OPENFABLAB_RES_FILE', __DIR__ . '/historical-wordpress/openfablab-reservations.php');
define('OPENFABLAB_RES_PATH', dirname(OPENFABLAB_RES_FILE) . '/');
class WP_Error {
    public function __construct(public $code, public $message, public $data = []) {}
    public function get_error_message() { return $this->message; }
}
class WP_REST_Request {
    public function __construct(private $data) {}
    public function get_body() { return json_encode($this->data); }
}
function is_wp_error($value) { return $value instanceof WP_Error; }
function sanitize_text_field($value) { return trim(strip_tags($value)); }
function sanitize_email($value) { return filter_var($value, FILTER_VALIDATE_EMAIL) ? $value : ''; }
function is_email($value) { return filter_var($value, FILTER_VALIDATE_EMAIL); }
function wp_date($format, $timestamp = null, $zone = null) {
    return (new DateTimeImmutable('@' . ($timestamp ?? time())))->setTimezone($zone ?? new DateTimeZone('Europe/Paris'))->format($format);
}
function current_time($format, $gmt = false) { return gmdate('Y-m-d H:i:s'); }
function get_option($name, $default = '') { return $default; }
function get_bloginfo($name) { return 'Atelier Test'; }
function add_query_arg($key, $value = null, $url = null) {
    return is_array($key) ? $value . '?' . http_build_query($key) : $url . '?' . http_build_query([$key => $value]);
}
function admin_url($path) { return 'https://example.invalid/' . $path; }
function home_url($path) { return 'https://example.invalid' . $path; }
function wp_mail(...$args) { $GLOBALS['mails'][] = $args; return true; }
function wp_unslash($value) { return $value; }
function wp_timezone() { return new DateTimeZone('Europe/Paris'); }
function esc_html($value) { return htmlspecialchars((string) $value, ENT_QUOTES, 'UTF-8'); }
function esc_attr($value) { return esc_html($value); }
function esc_url($value) { return esc_html($value); }
function plugins_url($path, $file) { return 'https://example.invalid/plugin/' . $path; }
function nocache_headers() { header('Cache-Control: no-store'); }
function status_header($status) { http_response_code($status); }
function wp_nonce_field(...$args) { return '<input name="_wpnonce" value="test-nonce">'; }
function wp_verify_nonce($value, $action) { return $value === 'test-nonce'; }
class OpenFabLab_Database {
    public static function table($name) { return $name; }
    public static function event($environment, $type, $uuid) { $GLOBALS['events'][] = [$environment, $type, $uuid]; }
}
class MemoryDatabase {
    public $bookings = [], $tokens = [], $snapshot, $cancel_on_next_lock = false;
    public $animation = ['id'=>1, 'environment'=>'test', 'capacity'=>1, 'title'=>'Atelier <créatif>',
        'starts_at'=>'2099-11-12 13:00:00', 'ends_at'=>'2099-11-12 15:00:00', 'timezone'=>'Europe/Paris',
        'minimum_age'=>10, 'accompaniment_under_age'=>15, 'close_minutes'=>60];
    public function prepare($query, ...$args) { return [$query, $args]; }
    public function query($query) {
        if ($query === 'START TRANSACTION') { $this->snapshot = [$this->bookings, $this->tokens]; }
        if ($query === 'ROLLBACK') { [$this->bookings, $this->tokens] = $this->snapshot; }
        return 1;
    }
    public function get_row($prepared, $mode = null) {
        [$query, $args] = $prepared;
        if (str_contains($query, 'FROM animations')) {
            if ($this->cancel_on_next_lock) {
                foreach ($this->bookings as &$row) { $row['status'] = 'cancelled'; }
                // Simulate an earlier transaction committed before this lock was acquired.
                $this->snapshot = [$this->bookings, $this->tokens];
                $this->cancel_on_next_lock = false;
            }
            return $this->animation;
        }
        if (str_contains($query, 'FROM tokens')) {
            foreach ($this->tokens as $token) {
                if ($token['reservation_uuid']===$args[0] && $token['token_type']===$args[1]
                    && $token['token_hash']===$args[2] && empty($token['used_at']) && $token['expires_at']>$args[3]) { return $token; }
            }
            return null;
        }
        return $this->bookings[$args[0]] ?? null;
    }
    public function get_results($prepared, $mode = null) {
        [$query, $args] = $prepared;
        return array_values(array_filter($this->bookings, fn($row) => $row['animation_id'] === $args[0]
            && (str_contains($query, 'group_uuid') ? $row['group_uuid'] === $args[1] : $row['uuid'] === $args[1])));
    }
    public function get_var($prepared) {
        return count(array_filter($this->bookings, fn($row) => in_array($row['status'], ['confirmed','offer_pending','present','absent'], true)));
    }
    public function update($table, $changes, $where) {
        $rows = &$this->{$table === 'reservations' ? 'bookings' : 'tokens'};
        foreach ($rows as &$row) {
            $matches = true;
            foreach ($where as $key=>$value) { $matches = $matches && ($row[$key] ?? null) === $value; }
            if ($matches) { $row = array_merge($row, $changes); }
        }
        return 1;
    }
    public function insert($table, $data) { $this->tokens[] = ['id'=>count($this->tokens)+1] + $data; return 1; }
}
require OPENFABLAB_RES_PATH . 'includes/class-openfablab-slots.php';
require OPENFABLAB_RES_PATH . 'includes/class-openfablab-emails.php';
require OPENFABLAB_RES_PATH . 'includes/class-openfablab-bookings.php';
require OPENFABLAB_RES_PATH . 'includes/class-openfablab-api.php';
function fixture($status='waitlisted', $group=null, $uuid=null) {
    $uuid = $uuid ?? '00000000-0000-4000-8000-000000000001';
    return ['uuid'=>$uuid, 'animation_id'=>1, 'environment'=>'test', 'status'=>$status, 'group_uuid'=>$group,
        'first_name'=>'Anne <TEST>', 'last_name'=>'LOCAL', 'email'=>'anne@example.invalid', 'phone'=>'0600000000',
        'birth_year'=>1990, 'public_id'=>null, 'is_present'=>null, 'offer_expires_at'=>null];
}
function reset_fixture($status='waitlisted', $pair=false) {
    $GLOBALS['wpdb'] = new MemoryDatabase(); $GLOBALS['mails'] = []; $GLOBALS['events'] = [];
    $row = fixture($status, $pair ? 'pair' : null); $GLOBALS['wpdb']->bookings[$row['uuid']] = $row;
    if ($pair) { $row = fixture($status, 'pair', '00000000-0000-4000-8000-000000000002'); $GLOBALS['wpdb']->bookings[$row['uuid']] = $row; }
}
function command($action, $extra=[]) {
    return OpenFabLab_API::sync_commands(new WP_REST_Request($extra + ['environment'=>'test',
        'uuid'=>'00000000-0000-4000-8000-000000000001', 'action'=>$action]));
}
if (($argv[1] ?? '') === 'cancel-page') {
    reset_fixture('confirmed'); $token = str_repeat('a', 64); $row = reset($wpdb->bookings);
    $wpdb->tokens[] = ['id'=>1, 'reservation_uuid'=>$row['uuid'], 'token_type'=>'cancel',
        'token_hash'=>hash('sha256', $token), 'expires_at'=>'2099-11-12 13:00:00', 'used_at'=>null];
    if (($argv[2] ?? '') === 'used') { $wpdb->tokens[0]['used_at'] = gmdate('Y-m-d H:i:s'); }
    if (($argv[2] ?? '') === 'expired') { $wpdb->tokens[0]['expires_at'] = '2000-01-01 00:00:00'; }
    $_REQUEST = ['booking'=>$row['uuid'], 'token'=>($argv[2] ?? '') === 'invalid' ? str_repeat('b',64) : $token];
    $_SERVER['REQUEST_METHOD'] = 'GET';
    OpenFabLab_Bookings::cancellation_page();
}
$tests = 0;
function check($condition, $message) { if (!$condition) { throw new RuntimeException($message); } ++$GLOBALS['tests']; }
reset_fixture();
check(command('confirm')['ok'] && reset($wpdb->bookings)['status']==='confirmed', 'waiting confirmation');
check(reset($wpdb->bookings)['is_present']===null, 'presence remains unset');
check(count($mails)===1 && command('confirm')['ok'] && count($mails)===1, 'retry idempotent, no duplicate email');
command('absent');
check(reset($wpdb->bookings)['status']==='confirmed' && reset($wpdb->bookings)['is_present']===0, 'absence separate');
command('present');
check(reset($wpdb->bookings)['status']==='confirmed' && reset($wpdb->bookings)['is_present']===1, 'presence separate');
reset_fixture('cancelled');
check(command('confirm')['confirmation']==='refused' && reset($wpdb->bookings)['status']==='cancelled', 'cancelled not reopened');
check(is_wp_error(command('present')), 'cancelled cannot attend');
reset_fixture('waitlisted', true);
check(command('confirm')['reason']==='capacity' && count(array_filter($wpdb->bookings, fn($r)=>$r['status']==='waitlisted'))===2, 'pair atomic refusal');
check(command('confirm', ['capacity_override'=>true])['ok'] && count(array_filter($wpdb->bookings, fn($r)=>$r['status']==='confirmed'))===2, 'explicit pair override');
reset_fixture('offer_pending');
check(command('confirm')['ok'] && reset($wpdb->bookings)['status']==='confirmed', 'held offer consumes no extra place');
reset_fixture('confirmed', true);
check(command('cancel')['ok'] && count(array_filter($wpdb->bookings, fn($r)=>$r['status']==='cancelled'))===2, 'group cancellation atomic');
check(is_wp_error(command('present')), 'cancelled group cannot become present');
reset_fixture('confirmed'); $wpdb->cancel_on_next_lock = true;
check(is_wp_error(command('present')) && reset($wpdb->bookings)['status']==='cancelled', 'concurrent cancellation not reopened by presence');
reset_fixture('waitlisted'); $wpdb->cancel_on_next_lock = true;
check(command('confirm')['reason']==='state' && reset($wpdb->bookings)['status']==='cancelled', 'concurrent cancellation not reopened by confirmation');
reset_fixture();
$row=fixture('absent', null, '00000000-0000-4000-8000-000000000002'); $wpdb->bookings[$row['uuid']]=$row;
check(command('confirm')['reason']==='capacity', 'legacy absent still reserves capacity');
check(is_wp_error(command('verify', ['environment'=>'production'])), 'environment isolation');
$validate = new ReflectionMethod(OpenFabLab_Bookings::class, 'validate_person');
$person = ['first_name'=>'Anne','last_name'=>'TEST','birth_year'=>1990,'email'=>'anne@example.invalid','phone'=>'0600000000'];
check(!is_wp_error($validate->invoke(null, $person)), 'valid required fields');
foreach (['email','phone','birth_year'] as $field) { $data=$person; unset($data[$field]); check(is_wp_error($validate->invoke(null,$data)), 'missing ' . $field); }
echo "$tests PHP checks passed\n";
