<?php
// Historical protocol-2 helpers remain tested with in-memory fixtures only.
// New public routes use the gateway, covered separately by test_wordpress_family.php.
$fixture_root = sys_get_temp_dir() . '/openfablab-wp-' . bin2hex(random_bytes(8)) . '/';
mkdir($fixture_root . 'wp-admin/includes', 0700, true);
file_put_contents($fixture_root . 'wp-admin/includes/upgrade.php', '<?php');
register_shutdown_function(function () use ($fixture_root) {
    unlink($fixture_root . 'wp-admin/includes/upgrade.php');
    rmdir($fixture_root . 'wp-admin/includes'); rmdir($fixture_root . 'wp-admin'); rmdir($fixture_root);
});
define('ABSPATH', $fixture_root); define('ARRAY_A', 'ARRAY_A');
define('MINUTE_IN_SECONDS', 60); define('YEAR_IN_SECONDS', 365 * 86400);
$options = ['openfablab_res_sync_secret' => str_repeat('fictional-only-', 5)];
$transients = []; $hooks = []; $queries = []; $tests = 0;
class WP_Error {
    public function __construct(public $code, public $message, public $data = []) {}
    public function get_error_message() { return $this->message; }
}
class WP_REST_Request {
    public function __construct(private $data, private $headers = [], private $route = '') {}
    public function get_body() { return json_encode($this->data); }
    public function get_header($name) { return $this->headers[$name] ?? ''; }
    public function get_method() { return 'POST'; }
    public function get_route() { return $this->route; }
    public function get_param($name) { return $this->data[$name] ?? null; }
}
class WP_REST_Response {
    public $headers = [];
    public function __construct(public $data, public $status = 200) {}
    public function header($name, $value) { $this->headers[$name] = $value; }
}
function is_wp_error($value) { return $value instanceof WP_Error; }
function get_option($name, $default = '') { return $GLOBALS['options'][$name] ?? $default; }
function update_option($name, $value, ...$unused) { $GLOBALS['options'][$name] = $value; }
function get_transient($name) { return $GLOBALS['transients'][$name] ?? false; }
function set_transient($name, $value, $duration) { $GLOBALS['transients'][$name] = $value; }
function wp_salt($type) { return 'fictional-test-salt'; }
function is_ssl() { return $GLOBALS['ssl'] ?? true; }
function sanitize_text_field($value) { return trim(strip_tags($value)); }
function sanitize_email($value) { return filter_var($value, FILTER_VALIDATE_EMAIL) ? $value : ''; }
function is_email($value) { return filter_var($value, FILTER_VALIDATE_EMAIL); }
function current_time($format, $gmt = false) { return gmdate('Y-m-d H:i:s'); }
function wp_date($format) { return gmdate($format); }
function wp_generate_uuid4() { return '00000000-0000-4000-8000-' . sprintf('%012d', ++$GLOBALS['uuid_counter']); }
function wp_generate_password(...$args) { return 'fixture'; }
function wp_json_encode($value) { return json_encode($value); }
function esc_html($value) { return htmlspecialchars((string) $value, ENT_QUOTES, 'UTF-8'); }
function esc_attr($value) { return esc_html($value); }
function esc_url_raw($value) { return $value; }
function esc_url($value) { return esc_html($value); }
function plugin_dir_path($file) { return dirname($file) . '/'; }
function plugins_url($path, $file) { return 'https://example.invalid/plugin/' . $path; }
function rest_url($path) { return 'https://example.invalid/wp-json/' . $path; }
function get_bloginfo($name) { return 'Atelier Test'; }
function current_user_can($capability) { return $GLOBALS['administrator'] ?? true; }
function is_user_logged_in() { return $GLOBALS['logged_in'] ?? true; }
function wp_die($text) { throw new RuntimeException($text); }
function esc_html__($text, $domain) { return esc_html($text); }
function wp_nonce_field(...$args) {}
function wp_verify_nonce($value, $action) { return $value === 'fixture-nonce' && $action === 'openfablab_res_test_maintenance'; }
function wp_unslash($value) { return $value; }
function checked($value, $expected, $echo) { return $value === $expected ? 'checked' : ''; }
function submit_button($text) { echo '<button>' . esc_html($text) . '</button>'; }
function shortcode_atts($defaults, $attributes, $tag) { return array_merge($defaults, $attributes); }
function wp_enqueue_style(...$args) {}
function wp_enqueue_script(...$args) {}
function wp_add_inline_script($handle, $script, $position) { $GLOBALS['inline_script'] = $script; }
function add_action($name, $callback) { $GLOBALS['hooks'][$name] = $callback; }
function add_filter(...$args) {}
function add_shortcode(...$args) {}
function register_activation_hook(...$args) {}
function register_deactivation_hook(...$args) {}
function register_rest_route(...$args) { $GLOBALS['routes'][] = $args; }
function dbDelta($sql) { $GLOBALS['queries'][] = $sql; }
function add_query_arg($args, $url) { return $url . '?' . http_build_query($args); }
function admin_url($path) { return 'https://example.invalid/' . $path; }
function home_url($path) { return 'https://example.invalid' . $path; }
function wp_mail(...$args) { $GLOBALS['mails'][] = $args; return true; }

class PublicMemoryDatabase {
    public $prefix = 'wp_', $options = 'wp_options', $directory = [], $bookings = [], $tokens = [], $nonces = [], $snapshot;
    public function esc_like($value) { return addcslashes($value, '_%\\'); }
    public $animation = ['id'=>1, 'service_id'=>1, 'environment'=>'test', 'published'=>1, 'capacity'=>5,
        'title'=>'Atelier test', 'description'=>'', 'starts_at'=>'2099-11-12 13:00:00',
        'ends_at'=>'2099-11-12 15:00:00', 'timezone'=>'Europe/Paris', 'minimum_age'=>10,
        'accompaniment_under_age'=>15, 'close_minutes'=>60, 'signup_open_at'=>null,
        'audience'=>'registered', 'waitlist_enabled'=>1];
    public function get_charset_collate() { return ''; }
    public function prepare($sql, ...$params) { return [$sql, $params]; }
    public function query($query) {
        if (is_array($query)) {
            if (str_contains($query[0], 'INSERT IGNORE')) {
                if (isset($this->nonces[$query[1][0]])) { return 0; }
                $this->nonces[$query[1][0]] = true;
            }
            return 1;
        }
        if ($query === 'START TRANSACTION') { $this->snapshot = [$this->directory, $this->bookings, $this->tokens]; }
        if ($query === 'ROLLBACK') { [$this->directory, $this->bookings, $this->tokens] = $this->snapshot; }
        return 1;
    }
    public function get_row($prepared, $mode = null) {
        [$sql, $args] = $prepared;
        if (str_contains($sql, 'SHOW TABLE')) { return (object) ['Engine'=>'InnoDB']; }
        if (str_contains($sql, 'openfablab_directory')) {
            foreach ($this->directory as $row) {
                if ($row['environment']===$args[0] && $row['public_id']===$args[1] && $row['active']) { return $row; }
            }
            return null;
        }
        if (str_contains($sql, 'openfablab_animations')) {
            return $this->animation['environment'] === $args[0] ? $this->animation : null;
        }
        if (str_contains($sql, 'openfablab_reservations')) { return $this->bookings[$args[0]] ?? null; }
        return null;
    }
    public function get_var($prepared) {
        if (str_contains($prepared[0], 'identity_key')) { return null; }
        return count($this->bookings);
    }
    public function get_results($prepared, $mode = null) {
        if (str_contains($prepared[0], 'FROM wp_openfablab_animations')) {
            return $this->animation['environment'] === $prepared[1][0] ? [$this->animation + ['occupied'=>0]] : [];
        }
        return [];
    }
    public function delete($table, $where) {
        $this->directory = array_values(array_filter($this->directory, fn($row)=>$row['environment']!==$where['environment']));
        return 1;
    }
    public function insert($table, $row) {
        if (str_ends_with($table, '_directory')) { $this->directory[] = $row; }
        if (str_ends_with($table, '_reservations')) { $this->bookings[$row['uuid']] = $row; }
        if (str_ends_with($table, '_tokens')) { $this->tokens[] = $row; }
        return 1;
    }
}
$wpdb = new PublicMemoryDatabase(); $uuid_counter = 0;
require dirname(__DIR__) . '/wordpress/openfablab-reservations/openfablab-reservations.php';
function check($condition, $message) {
    if (!$condition) { throw new RuntimeException($message); }
    ++$GLOBALS['tests'];
}
// Upgrade a first 2.5.0 build without dropping any existing tables.
$options['openfablab_res_schema_version'] = '2.5.0'; $hooks['plugins_loaded']();
check($options['openfablab_res_schema_version']===OPENFABLAB_RES_SCHEMA_VERSION, 'corrective schema upgrade');
$schema = implode("\n", $queries);
foreach (['first_name varchar(80)', 'last_name varchar(80)', 'email varchar(254)', 'phone varchar(40)'] as $column) {
    check(str_contains($schema, $column), 'private directory column ' . $column);
}
check(!str_contains($schema, 'DROP '), 'non-destructive schema');
$queries = []; $hooks['plugins_loaded'](); check(!$queries, 'schema upgrade idempotent');
$secret = $options['openfablab_res_sync_secret'];
$user = ['public_id'=>'1234', 'active'=>true, 'first_name'=>'Élise-Anne', 'last_name'=>'DU PONT',
    'birth_year'=>1990, 'email'=>'elise@example.invalid', 'phone'=>'+33600000000', 'category'=>'user',
    'email_hmac'=>hash_hmac('sha256', 'contact/v1|email|elise@example.invalid', $secret),
    'phone_hmac'=>hash_hmac('sha256', 'contact/v1|phone|+33600000000', $secret)];
foreach (['test', 'production'] as $env) {
    check(OpenFabLab_API::sync_directory(new WP_REST_Request(['environment'=>$env, 'users'=>[$user]]))['ok'], 'sync ' . $env);
}
$original = $wpdb->directory;
function verify($id='1234', $email='', $phone='', $env='test') {
    $response=new WP_REST_Response(OpenFabLab_Bookings::verify([
        'environment'=>$env, 'public_id'=>$id, 'email'=>$email, 'phone'=>$phone]));
    $response->header('Cache-Control','private, no-store, max-age=0');
    $response->header('Referrer-Policy','no-referrer');
    return $response;
}
$generic = verify('9999', 'elise@example.invalid')->data;
foreach ([verify('1234','wrong@example.invalid'), verify('1234','', '0611111111'),
          verify('', 'elise@example.invalid'), verify('1234'), verify('bad', 'elise@example.invalid')] as $response) {
    check($response->data===$generic, 'indistinguishable invalid verification');
}
check(array_keys($generic)===['status','message'], 'no ID, identity, age or contact disclosed on failure');
check(OpenFabLab_Bookings::verify(['environment'=>'test','public_id'=>['1234'],'email'=>'elise@example.invalid'])===$generic, 'malformed verification generic without warning');
check(verify('1234',str_repeat('a',255))->data===$generic, 'oversized verification generic');
$wpdb->directory[0]['active'] = 0;
check(verify('1234','elise@example.invalid')->data===$generic, 'inactive user not disclosed');
$wpdb->directory = $original;
foreach ([['elise@example.invalid',''], ['', '0600000000'], ['elise@example.invalid','0600000000'],
          ['elise@example.invalid','0611111111'], ['wrong@example.invalid','0600000000']] as [$email,$phone]) {
    $response = verify('1234', $email, $phone);
    check($response->data['status']==='matched', 'one matching contact suffices');
    foreach (['first_name','last_name','birth_year','email','phone'] as $field) {
        check($response->data[$field]===$user[$field], 'prefill ' . $field);
    }
}
check($response->data['masked_identity']==='É****-A*** D* P***', 'unicode composite masking');
check(OpenFabLab_Bookings::mask_name('A É')==='A* É*', 'short names masked');
check(OpenFabLab_Bookings::mask_name("E\u{0301}lise") === "E\u{0301}****", 'combining accent not split');
check($response->headers['Cache-Control']==='private, no-store, max-age=0', 'verification not cached');
check($response->headers['Referrer-Policy']==='no-referrer', 'no referrer');
$transients = []; $_SERVER['REMOTE_ADDR'] = '192.0.2.1';
$ssl=false;
check(OpenFabLab_API::public_permission(new WP_REST_Request([]))->data['status']===403, 'plaintext HTTP rejected');
$ssl=true;
for ($i=0; $i<15; $i++) { check(OpenFabLab_API::public_permission(new WP_REST_Request([]))===true, 'allowed attempt'); }
check(OpenFabLab_API::public_permission(new WP_REST_Request([]))->data['status']===429, 'rate limit');
check(!str_contains(json_encode(array_keys($transients)), '192.0.2.1'), 'hashed limiter key');
$token = verify('1234','elise@example.invalid')->data['verification_token'];
$booking = ['environment'=>'test','service_id'=>1,'public_id'=>'1234', 'first_name'=>'Autre prénom',
    'last_name'=>'AUTRE', 'birth_year'=>1990,'email'=>'changed@example.invalid','phone'=>'0611111111',
    'verification_token'=>$token];
$saved = OpenFabLab_Bookings::reserve($booking);
check(!is_wp_error($saved) && $saved['status']==='confirmed', 'edited contacts can reserve: ' . (is_wp_error($saved) ? $saved->message : ''));
check(reset($wpdb->bookings)['link_status']==='matched', 'verified account retained after edits');
check($wpdb->directory===$original, 'reservation never modifies directory');
foreach (['first_name','last_name','birth_year','email','phone'] as $field) {
    $incomplete = $booking; $incomplete[$field] = '';
    check(is_wp_error(OpenFabLab_Bookings::reserve($incomplete)), 'required final field ' . $field);
}
$method = new ReflectionMethod(OpenFabLab_Bookings::class, 'verified_identity'); $method->setAccessible(true);
$unverified = ['status'=>'needs_review','public_id'=>'1234'];
check($method->invoke(null,'production','1234',$token,$unverified)===$unverified, 'proof bound to environment');
check($method->invoke(null,'test','5678',$token,$unverified)===$unverified, 'proof bound to ID');
check($method->invoke(null,'test','1234',$token . 'x',$unverified)===$unverified, 'tampered proof rejected');
$parts=explode('.', $token); $parts[0]=(string)(time()-1);
$parts[2]=hash_hmac('sha256', "prefill/v1|test|1234|{$parts[0]}|{$parts[1]}", $secret);
check($method->invoke(null,'test','1234',implode('.',$parts),$unverified)===$unverified, 'expired proof rejected');
$wpdb->directory[0]['active']=0;
check($method->invoke(null,'test','1234',$token,$unverified)===$unverified, 'inactive proof rejected');
$wpdb->directory=$original;
// A rejected private snapshot cannot erase the existing directory.
$bad=$user; $bad['email']=str_repeat('a',255);
check(is_wp_error(OpenFabLab_API::sync_directory(new WP_REST_Request(['environment'=>'test','users'=>[$bad]]))), 'oversized private snapshot refused');
check($wpdb->directory===$original, 'failed snapshot rolls back');
// Required companion fields are also checked by reserve, not just by JS.
$saved_animation=$wpdb->animation;
$wpdb->animation['audience']='all';
$wpdb->animation['starts_at']=gmdate('Y-m-d H:i:s',time()+365*86400);
$wpdb->animation['ends_at']=gmdate('Y-m-d H:i:s',time()+365*86400+7200);
$child=$booking; $child['public_id']=''; $child['birth_year']=(int)gmdate('Y')-12;
$child['companion']=['first_name'=>'Parent','last_name'=>'TEST','birth_year'=>1990,'email'=>'parent@example.invalid','phone'=>'0622222222'];
foreach (['first_name','last_name','birth_year','email','phone'] as $field) {
    $incomplete=$child; $incomplete['companion'][$field]='';
    check(is_wp_error(OpenFabLab_Bookings::reserve($incomplete)), 'required companion field '.$field);
}
check(!is_wp_error(OpenFabLab_Bookings::reserve($child)), 'complete companion group accepted');
$wpdb->animation=$saved_animation;
check(count(OpenFabLab_Bookings::public_animations('test'))===1, 'Test animation on Test');
check(OpenFabLab_Bookings::public_animations('production')===[], 'Test hidden on Normal');
$wpdb->animation['environment']='production';
check(count(OpenFabLab_Bookings::public_animations('production'))===1, 'Normal animation on Normal');
check(OpenFabLab_Bookings::public_animations('test')===[], 'Normal hidden on Test');
OpenFabLab_API::register();
check(count(array_filter($routes, fn($r)=>str_contains($r[1], 'directory') && $r[2]['permission_callback']===[OpenFabLab_API::class,'private_permission']))===1, 'directory endpoint HMAC private only');
check(!array_filter($routes, fn($r)=>str_contains($r[1], 'public/directory')), 'no public directory route');
$unsigned=new WP_REST_Request(['environment'=>'test','users'=>[$user]], [], '/openfablab/v1/sync/directory');
check(is_wp_error(OpenFabLab_API::private_permission($unsigned)), 'unsigned directory request refused');
$body=['environment'=>'test','users'=>[$user]]; $timestamp=(string)time(); $nonce=str_repeat('a',32);
$signature=hash_hmac('sha256', "$timestamp\n$nonce\nPOST\n/openfablab/v1/sync/directory\n".hash('sha256',json_encode($body)), $secret);
$signed=new WP_REST_Request($body,['x-openfablab-timestamp'=>$timestamp,'x-openfablab-nonce'=>$nonce,'x-openfablab-signature'=>$signature],'/openfablab/v1/sync/directory');
check(OpenFabLab_API::private_permission($signed)===true, 'valid signed directory request accepted');
check(is_wp_error(OpenFabLab_API::private_permission($signed)), 'nonce replay refused');
$wrong_nonce=str_repeat('b',32);
$wrong_signature=hash_hmac('sha256', "$timestamp\n$wrong_nonce\nPOST\n/openfablab/v1/sync/directory\n".hash('sha256',json_encode($body)), 'fictional-incorrect-secret');
$wrong_signed=new WP_REST_Request($body,['x-openfablab-timestamp'=>$timestamp,'x-openfablab-nonce'=>$wrong_nonce,'x-openfablab-signature'=>$wrong_signature],'/openfablab/v1/sync/directory');
check(is_wp_error(OpenFabLab_API::private_permission($wrong_signed)), 'incorrect secret refused without changing synchronization settings');
$html = openfablab_res_shortcode(['environment'=>'test']);
check(!str_contains($html . $inline_script, 'Élise') && !str_contains($html . $inline_script, 'elise@example.invalid'), 'initial public HTML has no directory PII');
check(!str_contains($html, 'openfablab-test-maintenance'), 'maintenance not public');
check(OPENFABLAB_RES_VERSION==='2.8.0'&&OPENFABLAB_RES_SCHEMA_VERSION==='2.6.0', 'legacy storage retained without destructive upgrade');
$_SERVER['REQUEST_METHOD']='GET'; ob_start(); openfablab_res_admin_page(); $admin=ob_get_clean();
foreach (['Normal :','Test :','Shortcodes des pages de réservation', 'Réservations normales', 'Réservations de test', 'data-openfablab-copy'] as $text) {
    check(str_contains($admin, $text), 'admin displays ' . $text);
}
check(str_contains($admin, 'environment=&quot;production&quot;') && str_contains($admin,'environment=&quot;test&quot;'), 'both exact shortcodes');
check(!str_contains($admin, 'Production') && !str_contains($admin, $secret), 'no old human label or secret');
check(str_contains($admin,'Outils de données Test')&&str_contains($admin,'Analyser les données Test'), 'private tools available in existing settings');
$settings_before=$options;
$_SERVER['REQUEST_METHOD']='POST';
$_POST=['openfablab_test_tool'=>'clean','environment'=>'production','service_id'=>'29','_wpnonce'=>'fixture-nonce',
    'openfablab_generate_secret'=>'1','from_name'=>'malicious maintenance request'];
ob_start(); openfablab_res_admin_page(); $refused=ob_get_clean();
check(str_contains($refused,'seul l’environnement Test'), 'crafted Normal maintenance request refused');
check($settings_before===$options, 'maintenance POST never saves settings or regenerates secret');
$_POST=['openfablab_test_tool'=>'analyse','environment'=>'test','service_id'=>'29','_wpnonce'=>'bad'];
ob_start(); openfablab_res_admin_page(); $refused=ob_get_clean();
check(str_contains($refused,'nonce invalide')&&$settings_before===$options, 'maintenance nonce isolated from settings');
$_POST=[]; $_SERVER['REQUEST_METHOD']='GET';
$administrator=false; $denied=false;
try { openfablab_res_admin_page(); } catch (RuntimeException $e) { $denied=true; }
check($denied, 'settings restricted to administrator');
if (($argv[1] ?? '')==='admin-html') { echo $admin; }
else { echo "PHP public: $tests checks passed\n"; }
