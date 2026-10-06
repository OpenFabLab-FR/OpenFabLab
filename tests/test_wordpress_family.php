<?php
// Real gateway/reset classes, wholly fictional WordPress/database fixtures.
define('ABSPATH', '/fictional/');define('ARRAY_A', 'ARRAY_A');
$tests=0;$options=['openfablab_res_core_url'=>'https://example.invalid/stat','openfablab_res_sync_secret'=>'fictional-shared-secret'];
$transients=[];$allowed=true;$nonce_ok=true;$core_history=['past_animations'=>25,'users'=>50,'billing'=>7];
class WP_Error {public function __construct(public $code, public $message, public $data=[]) {}}
class WP_REST_Response {public $headers=[];public function __construct(public $data) {}public function header($key,$value) {$this->headers[$key]=$value;}}
function assert_family($condition,$label) {global $tests;if (!$condition) {throw new RuntimeException($label);}++$tests;}
function get_option($key,$default='') {return $GLOBALS['options'][$key]??$default;}
function get_transient($key) {return $GLOBALS['transients'][$key]??false;}
function set_transient($key,$value,$duration) {$GLOBALS['transients'][$key]=$value;}
function delete_transient($key) {unset($GLOBALS['transients'][$key]);}
function get_current_user_id() {return 7;}
function current_user_can($cap) {assert_family($cap==='manage_options','admin-only permission');return $GLOBALS['allowed'];}
function check_admin_referer($action) {assert_family($action==='openfablab_legacy_reset','reset nonce scope');if (!$GLOBALS['nonce_ok']) {throw new RuntimeException('invalid nonce');}}
function wp_die($message) {throw new RuntimeException($message);}
function wp_json_encode($data) {return json_encode($data);}
function wp_salt($scope) {return 'fictional-auth-salt';}
function is_wp_error($value) {return $value instanceof WP_Error;}
function wp_remote_retrieve_response_code($response) {return $response['status'];}
function wp_remote_retrieve_body($response) {return $response['body'];}
function admin_url($path) {return 'https://example.invalid/wp-admin/'.$path;}
function wp_safe_remote_post($url,$args) {
    $GLOBALS['remote']=[$url,$args];
    assert_family($args['sslverify']===true && $args['redirection']===0,'TLS verification and no redirects');
    $route=substr($url,strpos($url,'/api/'));
    $h=$args['headers'];$canonical=$h['X-OpenFabLab-Timestamp']."\n".$h['X-OpenFabLab-Nonce']."\nPOST\n".$route."\n".hash('sha256',$args['body']);
    assert_family(hash_equals(hash_hmac('sha256',$canonical,$GLOBALS['options']['openfablab_res_sync_secret']),$h['X-OpenFabLab-Signature']),'signature exactly matches core');
    return $GLOBALS['response'];
}
class OpenFabLab_Database {
    public static function table($name) {if (!in_array($name,['tokens','events','directory','nonces','reservations','animations'],true)) {throw new RuntimeException('unexpected table');}return 'wp_openfablab_'.$name;}
    public static function tables_are_innodb() {return $GLOBALS['innodb']??true;}
}
class FamilyMemoryDB {
    public $last_error='';public $tables=[];public $queries=[];public $prior;public $fail=null;
    public function __construct() {foreach (['tokens','events','directory','nonces','reservations','animations'] as $name) {$this->tables['wp_openfablab_'.$name]=[['id'=>1,'fictional'=>$name]];}}
    public function get_results($sql,$format) {assert_family($format===ARRAY_A,'private backup rows');$this->queries[]=$sql;preg_match('/FROM ([a-z_]+)/',$sql,$m);return $this->tables[$m[1]];}
    public function query($sql) {
        $this->queries[]=$sql;if ($sql===$this->fail) {return false;}
        if ($sql==='START TRANSACTION') {$this->prior=$this->tables;}
        if ($sql==='ROLLBACK') {$this->tables=$this->prior;}
        if (str_starts_with($sql,'DELETE FROM ')) {$this->tables[substr($sql,12)]=[];}
        return 1;
    }
}
require __DIR__.'/historical-wordpress/includes/class-openfablab-family-gateway.php';
require __DIR__.'/historical-wordpress/includes/class-openfablab-legacy-reset.php';
// The gateway is now a transport adapter, never an HTTP client of the NAS.
class OpenFabLab_Relay {
    public static function public_catalogue($env) {
        assert_family(in_array($env,['test','production'],true),'explicit catalogue environment');
        return new WP_REST_Response(['animations'=>[]]);
    }
    public static function enqueue($action,$data) {
        $GLOBALS['deposited']=[$action,$data];
        if (!in_array($action,['identify','contact','reserve','view','cancel','accept','decline'],true)) return new WP_Error('invalid','Unknown action',['status'=>400]);
        $answer=new WP_REST_Response(['state'=>'pending','request_key'=>$data['request_key']??'']);
        $answer->header('Cache-Control','private, no-store');return $answer;
    }
}
foreach (['identify','contact','reserve','view','cancel','accept','decline'] as $action) {
    $data=['environment'=>'production','participants'=>['opaque1','opaque2','opaque3'],'request_key'=>'fictional-key'];
    $value=OpenFabLab_Family_Gateway::call($action,$data);
    assert_family($value instanceof WP_REST_Response,'accepted only as a queued request');
    assert_family($value->data['state']==='pending'&&!isset($value->data['status']),'no premature confirmation');
    assert_family($deposited===[$action,$data],'selection forwarded unchanged to queue');
    assert_family(str_contains($value->headers['Cache-Control'],'no-store'),'private result not cached');
    assert_family(!isset($GLOBALS['remote']),'no WordPress to core HTTP request');
}
$options['openfablab_res_core_url']='';$value=OpenFabLab_Family_Gateway::call('catalogue',['environment'=>'test']);
assert_family($value instanceof WP_REST_Response,'empty inbound URL does not break catalogue');
$options['openfablab_res_core_url']='http://unreachable.invalid';$value=OpenFabLab_Family_Gateway::call('catalogue',['environment'=>'production']);
assert_family($value instanceof WP_REST_Response,'historical core URL ignored');
assert_family(OpenFabLab_Family_Gateway::call('delete',[])->data['status']===400,'gateway cannot purge core');
$wpdb=new FamilyMemoryDB();$original_options=$options;$original_core=$core_history;
$snapshot=new ReflectionMethod(OpenFabLab_Legacy_Reset::class,'snapshot');$digest=new ReflectionMethod(OpenFabLab_Legacy_Reset::class,'stable_digest');
$saved=$snapshot->invoke(null);$transients['openfablab_legacy_reset_7']=$digest->invoke(null,$saved);
$_POST=['confirmation'=>'NETTOYER LE PLUGIN','backup_saved'=>'1'];
function refused($label) {global $wpdb;try {OpenFabLab_Legacy_Reset::reset();throw new LogicException('unexpected success');}catch (LogicException $e) {throw $e;}catch (RuntimeException $e) {assert_family(true,$label);}}
$allowed=false;refused('nonadministrator refused');$allowed=true;
$nonce_ok=false;refused('bad nonce refused');$nonce_ok=true;
$_POST['confirmation']='wrong';refused('exact text required');$_POST['confirmation']='NETTOYER LE PLUGIN';
$_POST['backup_saved']='';refused('backup acknowledged');$_POST['backup_saved']='1';
$saved_grant=$transients['openfablab_legacy_reset_7'];unset($transients['openfablab_legacy_reset_7']);refused('download required');$transients['openfablab_legacy_reset_7']=$saved_grant;
$wpdb->tables['wp_openfablab_reservations'][]=['id'=>2,'fictional'=>'changed'];
refused('changed reservations refuse reset');assert_family(count($wpdb->tables['wp_openfablab_reservations'])===2,'rollback preserves new rows');
$wpdb->tables['wp_openfablab_reservations']=$saved['reservations'];
$wpdb->fail='DELETE FROM wp_openfablab_reservations';refused('delete failure rollback');
assert_family($wpdb->tables===$wpdb->prior,'all six tables rolled back after partial failure');$wpdb->fail=null;
// Ephemeral anti-replay rows may change, never the historical data.
$wpdb->tables['wp_openfablab_nonces'][]=['id'=>2,'fictional'=>'new nonce'];
function wp_safe_redirect($url) {
    global $wpdb,$original_options,$original_core,$options,$core_history,$tests;
    assert_family(str_contains($url,'legacy_reset=done'),'local admin redirect');
    assert_family(array_sum(array_map('count',$wpdb->tables))===0,'exact plugin storage emptied');
    assert_family($options===$original_options,'settings and shared secret unchanged');
    assert_family($core_history===$original_core,'OpenFabLab history unchanged');
    assert_family(end($wpdb->queries)==='COMMIT','transaction committed');
    assert_family(get_transient('openfablab_legacy_reset_7')===false,'reset cannot be replayed');
    echo $tests." family gateway/reset checks passed\n";
}
OpenFabLab_Legacy_Reset::reset();
