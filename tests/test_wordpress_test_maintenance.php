<?php
// Actual maintenance class, real SQLite transactions in memory, WP stubs. No network.
define('ABSPATH', __DIR__); define('ARRAY_A', 'ARRAY_A');
class WP_Error {
    public function __construct(public $code, public $message) {}
    public function get_error_message() { return $this->message; }
}
function is_wp_error($value) { return $value instanceof WP_Error; }
function is_user_logged_in() { return $GLOBALS['logged_in']; }
function current_user_can($cap) { return $cap === 'manage_options' && $GLOBALS['administrator']; }
function get_current_user_id() { return $GLOBALS['actor']; }
function wp_verify_nonce($nonce, $action) { return $nonce === 'fixture-nonce' && $action === 'openfablab_res_test_maintenance'; }
function wp_nonce_field($action) { echo '<input type="hidden" name="_wpnonce" value="fixture-nonce">'; }
function wp_json_encode($value) { return json_encode($value); }
function wp_salt($type) { return 'fixture-only-nonce-salt'; }
function wp_generate_uuid4() { return '00000000-0000-4000-8000-' . sprintf('%012d', ++$GLOBALS['audit_counter']); }
function esc_html($text) { return htmlspecialchars((string) $text, ENT_QUOTES, 'UTF-8'); }
function esc_attr($text) { return esc_html($text); }
class OpenFabLab_Database {
    public static function table($name) { return 'wp_openfablab_' . $name; }
    public static function event(...$args) { throw new RuntimeException('A NAS event must never be generated'); }
}
function wp_mail(...$args) { throw new RuntimeException('A customer email must never be sent'); }

class MaintenanceDatabase {
    public $pdo, $options = 'wp_options', $last_error = '', $history = [], $fail = '', $engines = [];
    public function __construct() {
        $this->pdo = new PDO('sqlite::memory:');
        $this->pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $this->pdo->exec('CREATE TABLE wp_openfablab_animations (id INTEGER PRIMARY KEY, service_id INTEGER, environment TEXT, title TEXT, starts_at TEXT, ends_at TEXT, timezone TEXT, capacity INTEGER, updated_at TEXT)');
        $this->pdo->exec('CREATE TABLE wp_openfablab_reservations (id INTEGER PRIMARY KEY, uuid TEXT UNIQUE, animation_id INTEGER, environment TEXT, first_name TEXT, last_name TEXT, public_id TEXT, status TEXT, group_uuid TEXT, source TEXT, is_present INTEGER, offer_expires_at TEXT, created_at TEXT, updated_at TEXT, email TEXT, phone TEXT)');
        $this->pdo->exec('CREATE TABLE wp_openfablab_tokens (id INTEGER PRIMARY KEY, reservation_uuid TEXT, token_type TEXT, used_at TEXT, expires_at TEXT, token_hash TEXT)');
        $this->pdo->exec('CREATE TABLE wp_openfablab_events (id INTEGER PRIMARY KEY, environment TEXT, event_type TEXT, reservation_uuid TEXT, created_at TEXT)');
        $this->pdo->exec('CREATE TABLE wp_options (option_id INTEGER PRIMARY KEY AUTOINCREMENT, option_name TEXT UNIQUE, option_value TEXT, autoload TEXT)');
    }
    public function prepare($sql, ...$args) {
        $index = 0;
        return preg_replace_callback('/%[sd]/', function($m) use ($args, &$index) {
            $v = $args[$index++]; return $m[0] === '%d' ? (string)(int)$v : $this->pdo->quote((string)$v);
        }, $sql);
    }
    public function esc_like($text) { return addcslashes($text, '_%\\'); }
    private function execute($sql) {
        $this->history[] = $sql; $this->last_error = '';
        if ($this->fail && str_contains($sql, $this->fail)) { $this->last_error = 'fixture failure'; return false; }
        // SQLite adapter only removes MySQL row-lock syntax. SQL filters are actually executed.
        $sql = preg_replace('/ FOR UPDATE$/', '', $sql);
        if (str_contains($sql, 'WHERE option_name LIKE ')) { $sql = str_replace('\\_', '_', $sql); }
        try { return $this->pdo->query($sql); }
        catch (Throwable $e) { $this->last_error = 'fixture failure'; return false; }
    }
    public function get_row($sql, $mode = null) {
        if (preg_match("/SHOW TABLE STATUS WHERE Name = '([^']+)'/", $sql, $m)) {
            $this->history[] = $sql; $this->last_error = '';
            return (object)['Engine' => $this->engines[$m[1]] ?? 'InnoDB'];
        }
        $q = $this->execute($sql); if (!$q) return null;
        $row = $q->fetch(PDO::FETCH_ASSOC); return !$row ? null : ($mode === ARRAY_A ? $row : (object)$row);
    }
    public function get_results($sql, $mode = null) { $q = $this->execute($sql); return $q ? $q->fetchAll(PDO::FETCH_ASSOC) : null; }
    public function get_var($sql) { $q = $this->execute($sql); return $q ? $q->fetchColumn() : null; }
    public function query($sql) {
        $sql = $sql === 'START TRANSACTION' ? 'BEGIN TRANSACTION' : $sql;
        $q = $this->execute($sql); return $q === false ? false : 1;
    }
    public function update($table, $values, $where) {
        $sets = []; $filters = [];
        foreach ($values as $key => $value) { $sets[] = "$key = " . ($value === null ? 'NULL' : $this->pdo->quote((string)$value)); }
        foreach ($where as $key => $value) { $filters[] = $value === null ? "$key IS NULL" : "$key = " . $this->pdo->quote((string)$value); }
        $q = $this->execute("UPDATE $table SET " . implode(', ', $sets) . ' WHERE ' . implode(' AND ', $filters));
        return $q === false ? false : $q->rowCount();
    }
    public function insert($table, $row, $formats = []) {
        $q = $this->execute("INSERT INTO $table (" . implode(',', array_keys($row)) . ') VALUES ('
            . implode(',', array_map(fn($value) => $value === null ? 'NULL' : $this->pdo->quote((string)$value), array_values($row))) . ')');
        return $q === false ? false : $q->rowCount();
    }
    public function state() {
        $result = [];
        foreach (['animations','reservations','tokens','events'] as $table) {
            $result[$table] = $this->pdo->query("SELECT * FROM wp_openfablab_$table ORDER BY id")->fetchAll(PDO::FETCH_ASSOC);
        }
        $result['options'] = $this->pdo->query('SELECT * FROM wp_options ORDER BY option_id')->fetchAll(PDO::FETCH_ASSOC);
        return $result;
    }
}
require dirname(__DIR__) . '/wordpress/openfablab-reservations/includes/class-openfablab-test-maintenance.php';
$tests = 0;
function check($ok, $label) { if (!$ok) throw new RuntimeException($label); $GLOBALS['tests']++; }
function fixture() {
    $GLOBALS['wpdb'] = new MaintenanceDatabase(); $GLOBALS['logged_in'] = true;
    $GLOBALS['administrator'] = true; $GLOBALS['actor'] = 7; $GLOBALS['audit_counter'] = 0;
    $_SERVER['REQUEST_METHOD'] = 'POST';
    global $wpdb;
    foreach ([[1,29,'test','Atelier <TEST>',6],[2,30,'test','Autre animation Test',6],[3,29,'production','Normal protégé',6]] as [$id,$service,$env,$title,$capacity]) {
        $wpdb->insert('wp_openfablab_animations', ['id'=>$id,'service_id'=>$service,'environment'=>$env,'title'=>$title,
            'capacity'=>$capacity,'starts_at'=>'2099-10-08 08:30:00','ends_at'=>'2099-10-08 10:30:00',
            'timezone'=>'Europe/Paris','updated_at'=>'2026-09-30 08:00:00']);
    }
    foreach ([[1,1,'test','confirmed'],[2,1,'test','confirmed'],[3,1,'test','confirmed'],[4,1,'test','confirmed'],
              [5,1,'test','waitlisted'],[6,1,'test','cancelled'],[7,2,'test','confirmed'],[8,3,'production','confirmed']] as [$id,$anim,$env,$status]) {
        $uuid = sprintf('00000000-0000-4000-8000-%012d', $id);
        $wpdb->insert('wp_openfablab_reservations', ['id'=>$id,'uuid'=>$uuid,'animation_id'=>$anim,'environment'=>$env,
            'first_name'=>'Anne <TEST>','last_name'=>'FICTIF','public_id'=>'1234','status'=>$status,
            'group_uuid'=>null,'source'=>'online','is_present'=>null,'offer_expires_at'=>null,
            'created_at'=>$id===4 ? '2026-09-30 14:00:00' : '2026-09-29 12:00:00','updated_at'=>'2026-09-30 08:00:00',
            'email'=>'fixture-only@example.invalid','phone'=>'0600000000']);
        foreach (['cancel','offer'] as $type) {
            $wpdb->insert('wp_openfablab_tokens', ['id'=>$id*2+($type==='cancel'?0:1),'reservation_uuid'=>$uuid,
                'token_type'=>$type,'used_at'=>null,'expires_at'=>'2099-10-08 08:30:00','token_hash'=>'fixture-only-token-hash']);
        }
        $wpdb->insert('wp_openfablab_events', ['id'=>$id,'environment'=>$env,'event_type'=>'reservation_created',
            'reservation_uuid'=>$uuid,'created_at'=>'2026-09-29 12:00:00']);
    }
    $wpdb->history=[];
}
function request($action='analyse', $extra=[]) {
    return OpenFabLab_Test_Maintenance::handle_request($extra + ['openfablab_test_tool'=>$action,'environment'=>'test',
        'service_id'=>'29','_wpnonce'=>'fixture-nonce']);
}
function preview($ids=['1','2','3']) { return request('preview', ['reservation_ids'=>$ids]); }
function clean_input($preview, $ids=['1','2','3']) {
    return ['reservation_ids'=>$ids,'confirmation'=>'PURGER TEST 29','orphans_confirmed'=>'1',
        'preview_issued_at'=>(string)$preview['issued'],'preview_fingerprint'=>$preview['fingerprint']];
}
function clean($preview, $extra=[], $ids=['1','2','3']) { return request('clean', $extra + clean_input($preview,$ids)); }
function render($result) { ob_start(); OpenFabLab_Test_Maintenance::render($result); return ob_get_clean(); }

// Private HTML fixture for browser tests. Does not contact any site.
if (($argv[1] ?? '') === 'html') {
    fixture(); $mode=$argv[2] ?? 'analyse'; $result=request();
    if ($mode==='preview') $result=preview();
    if ($mode==='done') { $p=preview(); $result=clean($p); }
    if ($mode==='denied') $GLOBALS['administrator']=false;
    echo '<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        . '<style>body{margin:0;padding:16px;font:16px system-ui}.wrap{min-width:0;max-width:100%}table{border-collapse:collapse}th,td{padding:8px;vertical-align:top;border:1px solid #ddd}.button{padding:10px}input[type=checkbox]{width:24px;height:24px}code{font-size:12px}</style><div class="wrap">'
        . render($result) . '</div></html>'; exit;
}

fixture(); $before=$wpdb->state(); $a=request();
check(!is_wp_error($a) && $a['snapshot']['animation']['service_id']===29, 'Test analysis works');
check($a['snapshot']['occupied']===4 && $a['snapshot']['available']===2, '6 - 4 = 2, no hardcoded fixture result');
check(count($a['snapshot']['rows'])===6, 'includes cancelled and waitlisted for diagnosis');
check($before===$wpdb->state() && !array_filter($wpdb->history,fn($q)=>preg_match('/^(UPDATE|INSERT|DELETE|BEGIN)/',$q)), 'analysis read only');
check(!str_contains(json_encode($a),'fixture-only@example.invalid') && !str_contains(json_encode($a),'0600000000'), 'contacts never read');
check(!str_contains(json_encode($a),'fixture-only-token-hash'), 'token hashes never read');
$html=render($a);
foreach (['Outils de données Test','ID interne WordPress','Annulation :','Liste d’attente :','Places consommées :','Groupe / personnes liées','Création :','Modification :','Compte actuellement :'] as $label) check(str_contains($html,$label),'diagnostic '.$label);
check(!preg_match('/<input[^>]*type="checkbox"[^>]*checked/', $html), 'nothing preselected');
check(str_contains($html,'Anne &lt;TEST&gt;') && !str_contains($html,'Anne <TEST>'), 'names escaped');
check(!str_contains($html,'fixture-only-token-hash') && !str_contains($html,'fixture-only@example.invalid'), 'no secret or contacts in admin display');
$p=preview(); check(!is_wp_error($p)&&$p['plan']['places']===3 && count($p['plan']['links'])===6, 'preview selected places and both types of link');
check($before===$wpdb->state(), 'preview read only and no option/transient write');
check(str_contains(render($p),'PURGER TEST 29'), 'service-specific confirmation shown');
check(is_wp_error(request('preview', ['reservation_ids'=>[]])), 'empty selection refused');
check(is_wp_error(preview(['1','1'])), 'duplicate selection refused');
foreach ([['7'],['8'],['6'],['999'],['1 OR 1=1'],['-1'],[['1']]] as $ids) check(is_wp_error(preview($ids)), 'invalid, terminal, other animation or Normal selection refused');
foreach (['production','TEST','',null,['test']] as $env) check(is_wp_error(request('clean',['environment'=>$env])), 'environment rejected independently of UI');
foreach (['0','-1','29 OR 1=1',['29']] as $id) check(is_wp_error(request('analyse',['service_id'=>$id])), 'bad service id refused');
$_SERVER['REQUEST_METHOD']='GET'; check(is_wp_error(clean($p)), 'mutation GET refused'); $_SERVER['REQUEST_METHOD']='POST';
check(is_wp_error(clean($p,['_wpnonce'=>'bad'])), 'CSRF nonce refused');
$logged_in=false; check(is_wp_error(clean($p)) && render($p)==='', 'unauthenticated function and UI refused'); $logged_in=true;
$administrator=false; check(is_wp_error(clean($p))&&is_wp_error(OpenFabLab_Test_Maintenance::diagnose('test',29))&&render($p)==='', 'non-admin function and UI refused'); $administrator=true;
check(is_wp_error(OpenFabLab_Test_Maintenance::diagnose('production',29)), 'direct diagnostic rejects Normal');
foreach (['','PURGER TEST 30','purger test 29','PURGER TEST 29 '] as $text) check(is_wp_error(clean($p,['confirmation'=>$text])), 'confirmation exact');
check(is_wp_error(clean($p,['orphans_confirmed'=>'0'])), 'explicit orphan declaration required');
check(is_wp_error(clean($p,['preview_issued_at'=>(string)(time()-601)])), 'expired preview refused');
check(is_wp_error(clean($p,['preview_fingerprint'=>'forged'])), 'forged preview refused');
check(is_wp_error(clean($p,[],['1','2'])), 'selection changed after preview refused');
$actor=8; check(is_wp_error(clean($p)), 'preview bound to current administrator'); $actor=7;
check($before===$wpdb->state(), 'all refusals preserve every table');
$private_apply=new ReflectionMethod(OpenFabLab_Test_Maintenance::class,'apply'); $private_apply->setAccessible(true);
foreach ([['production','test'],['test','production']] as [$arg,$field]) {
    $refused=false; try {$private_apply->invoke(null,$arg,29,clean_input($p)+['environment'=>$field,'_wpnonce'=>'fixture-nonce']);} catch(DomainException $e){$refused=true;}
    check($refused && $before===$wpdb->state(),'direct mutation rejects production at both guards');
}

fixture(); $wpdb->pdo->exec("UPDATE wp_openfablab_reservations SET group_uuid='fixture-pair' WHERE id IN (1,2)");
check(is_wp_error(preview(['1'])), 'half group refused, no silent extra selection');
$p=preview(['1','2']); check(!is_wp_error($p)&&$p['plan']['places']===2, 'complete companion group occupies two seats');
check(!is_wp_error(clean($p,[],['1','2'])), 'complete group cancelled atomically');
fixture(); $wpdb->pdo->exec("UPDATE wp_openfablab_reservations SET status='waitlisted' WHERE id=1");
$p=preview(['1']); check($p['plan']['places']===0 && !is_wp_error(clean($p,[],['1'])), 'waitlist cancellation releases zero places');
foreach (['offer_pending','present','absent'] as $status) {
    fixture(); $wpdb->pdo->exec("UPDATE wp_openfablab_reservations SET status='$status' WHERE id=1");
    check(request()['snapshot']['occupied']===4 && preview(['1'])['plan']['places']===1,'counted '.$status);
}
fixture(); $p=preview(); $wpdb->pdo->exec("UPDATE wp_openfablab_animations SET capacity=7 WHERE id=1");
$changed=$wpdb->state(); check(is_wp_error(clean($p))&&$changed===$wpdb->state(),'changed capacity forces new preview');
fixture(); $p=preview(); $wpdb->pdo->exec("UPDATE wp_openfablab_reservations SET updated_at='2099-01-01 00:00:00' WHERE id=4");
$changed=$wpdb->state(); check(is_wp_error(clean($p))&&$changed===$wpdb->state(),'changed unselected reservation forces new preview');
fixture(); $p=preview(); $wpdb->pdo->exec("UPDATE wp_openfablab_tokens SET used_at='2026-09-30 10:00:00' WHERE id=2");
$changed=$wpdb->state(); check(is_wp_error(clean($p))&&$changed===$wpdb->state(),'changed links force new preview');
foreach (['UPDATE wp_openfablab_reservations','UPDATE wp_openfablab_tokens','INSERT INTO wp_options','COMMIT'] as $failure) {
    fixture(); $p=preview(); $before=$wpdb->state(); $wpdb->fail=$failure;
    check(is_wp_error(clean($p)),'injected failure refused '.$failure);
    check($before===$wpdb->state(),'transaction rollback includes audit and links '.$failure);
}
fixture(); $p=preview(); $before=$wpdb->state(); $wpdb->engines['wp_options']='MyISAM';
check(is_wp_error(clean($p))&&$before===$wpdb->state(),'nontransactional audit engine refused');
fixture(); $wpdb->pdo->exec("UPDATE wp_openfablab_reservations SET environment='production' WHERE id=1");
check(is_wp_error(request()),'cross-environment inconsistency refuses diagnosis and cleanup');

fixture(); $before=$wpdb->state(); $p=preview(); $result=clean($p);
check(!is_wp_error($result)&&$result['mode']==='done','targeted cleanup succeeds');
check($result['before']['occupied']===4&&$result['snapshot']['occupied']===1&&$result['snapshot']['available']===5,'before/after capacity correct');
$after=$wpdb->state();
check(count($after['reservations'])===count($before['reservations']),'history kept, no deletion');
foreach ([0,1,2] as $i) check($after['reservations'][$i]['status']==='cancelled','selected row cancelled');
check($before['animations']===$after['animations'],'all animations and capacities unchanged');
check(array_slice($before['reservations'],3)===array_slice($after['reservations'],3),'current NAS row, other Test and Normal unchanged');
check(count(array_filter($after['tokens'],fn($t)=>$t['id']>=2&&$t['id']<=7&&$t['used_at']!==null))===6,'selected cancellation and offer links invalidated');
check(array_slice($before['tokens'],6)===array_slice($after['tokens'],6),'unselected links unchanged');
check($before['events']===$after['events'],'no new NAS event, historic events preserved');
check(count($after['options'])===1,'one atomic administrator audit');
$audit=json_decode($after['options'][0]['option_value'],true);
check($audit['wordpress_user_id']===7&&$audit['environment']==='test'&&$audit['service_id']===29&&$audit['reservations_affected']===3&&$audit['places_released']===3,'audit actor scope and counts');
check(!preg_match('/Anne|FICTIF|1234|060000|fixture-only-token|email|phone|nonce|fingerprint/',json_encode($audit)),'audit contains no unnecessary PII or secrets');
check(!array_filter($wpdb->history,fn($q)=>preg_match('/^(DELETE|DROP|TRUNCATE)/i',$q)),'no destructive SQL');
check(str_contains(implode('\n',$wpdb->history),'FOR UPDATE'),'transaction row locks requested');
check(is_wp_error(clean($p))&&$after===$wpdb->state(),'resubmission cannot duplicate cleanup or audit');
check(str_contains(render($result),'Après : 1 occupées / 5 disponibles'),'dynamic result and audit displayed');
check(str_contains(render($result),'utilisateur WordPress #7'),'administrator journal is readable');
// The unchanged 2.5.1 tool also works with the additive 2.6.0 slot columns.
fixture();
$wpdb->query("ALTER TABLE wp_openfablab_animations ADD COLUMN booking_mode TEXT DEFAULT 'whole'");
$wpdb->query("ALTER TABLE wp_openfablab_animations ADD COLUMN slots_json TEXT DEFAULT '[]'");
$wpdb->query("ALTER TABLE wp_openfablab_reservations ADD COLUMN slot_uuid TEXT");
$wpdb->query("UPDATE wp_openfablab_animations SET booking_mode='slots' WHERE id=1");
$wpdb->query("UPDATE wp_openfablab_reservations SET slot_uuid='fixture-slot' WHERE animation_id=1");
$snapshot=request();check(!is_wp_error($snapshot),'diagnosis on additive slots schema');
$before=$wpdb->state();$p=preview();$result=clean($p);
check(!is_wp_error($result),'targeted slot cleanup supported');
$after=$wpdb->state();
check($before['animations']===$after['animations'],'slot animation and catalogue unchanged');
check(array_column($before['reservations'],'slot_uuid')===array_column($after['reservations'],'slot_uuid'),'historical slot references preserved');
check($before['events']===$after['events'],'slot maintenance no NAS event');
check(array_slice($before['reservations'],3)===array_slice($after['reservations'],3),'other slots current NAS and Normal preserved');
echo "$tests PHP maintenance checks passed\n";
