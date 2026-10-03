<?php
// Actual plugin classes against an isolated transactional SQLite wpdb adapter.
// MySQL row locks are asserted in SQL but need a real WP/InnoDB integration test.
require __DIR__.'/test_wordpress_slots.php';
require $plugin.'class-openfablab-reconciliation.php';
$tests=0;$wpdb=new SlotDatabase();$GLOBALS['email_test_options']=[];
define('OPENFABLAB_RES_VERSION','2.7.0');
function is_user_logged_in(){return$GLOBALS['logged']??true;}
function current_user_can($cap){return$GLOBALS['admin']??true;}
function get_current_user_id(){return 42;}
function delete_option($key){unset($GLOBALS['email_test_options'][$key]);return true;}
function check_admin_referer($action){if(!($GLOBALS['nonce']??true))throw new RuntimeException('nonce refused');}
function wp_die($text){throw new RuntimeException($text);}
$_SERVER['REQUEST_METHOD']='POST';
function snapshot($items,$env='test'){return OpenFabLab_Reconciliation::snapshot(new WP_REST_Request(['environment'=>$env,'animations'=>$items]));}
publish(payload(1,2,10,'test','whole'));publish(payload(2,2,10,'production','whole'));
$a=animation();
$wpdb->insert('wp_openfablab_reservations',['uuid'=>'fictional-current','environment'=>'test','animation_id'=>$a['id'],'status'=>'confirmed','first_name'=>'Camille','last_name'=>'EXEMPLE','email'=>'camille@example.invalid']);
$wpdb->insert('wp_openfablab_events',['environment'=>'test','event_type'=>'confirmed','reservation_uuid'=>'fictional-current']);
$wpdb->insert('wp_openfablab_tokens',['reservation_uuid'=>'fictional-current','token_type'=>'cancel','token_hash'=>'fictional-not-a-live-token']);
$private=[];foreach(['reservations','events','tokens']as$table)$private[$table]=$wpdb->get_results('SELECT * FROM wp_openfablab_'.$table);
check(snapshot([])['ok']===true,'authoritative empty catalogue repairs a lost deletion');
check((int)animation()['published']===0,'orphan animation hidden');
check((int)animation(2,'production')['published']===1,'other environment unchanged');
foreach($private as$table=>$rows)check($rows===$wpdb->get_results('SELECT * FROM wp_openfablab_'.$table),'keeps '.$table);
check(snapshot([])['ok']===true,'snapshot idempotent');
$p=payload(1,3,10,'test','whole')['animation'];
check(snapshot([$p])['ok']===true,'rebuild current catalogue');
check(OpenFabLab_Slots::used(animation())===1,'fresh WordPress booking preserved in capacity');
check(is_wp_error(snapshot([$p,$p])),'duplicate ID refused');
check(is_wp_error(snapshot([$p],'production')),'cross-environment snapshot refused');
check(is_wp_error(snapshot([],'bad')),'invalid environment refused');
$wpdb->fail='UPDATE wp_openfablab_animations';
check(is_wp_error(snapshot([])),'failed snapshot not acknowledged');$wpdb->fail='';
check((int)animation()['published']===1,'failed snapshot rolled back');
$wpdb->fail='UPDATE wp_openfablab_animations';
check(is_wp_error(OpenFabLab_API::sync_animations(new WP_REST_Request(['environment'=>'test','service_id'=>1,'command'=>'delete']))),'delete false not acknowledged');$wpdb->fail='';
$before=$wpdb->get_results('SELECT * FROM wp_openfablab_animations');
foreach([['logged',false],['admin',false],['nonce',false]]as[$key,$value]){
 $GLOBALS[$key]=$value;$refused=false;
 try{OpenFabLab_Reconciliation::handle_admin_request(['environment'=>'test','catalog_action'=>'purge','confirmation'=>'RESYNCHRONISER TEST']);}catch(Throwable$e){$refused=true;}
 check($refused,'security guard '.$key);unset($GLOBALS[$key]);
}
$_SERVER['REQUEST_METHOD']='GET';$refused=false;
try{OpenFabLab_Reconciliation::handle_admin_request(['environment'=>'test','catalog_action'=>'refresh']);}catch(Throwable$e){$refused=true;}
check($refused,'GET cannot mutate');$_SERVER['REQUEST_METHOD']='POST';
$refused=false;try{OpenFabLab_Reconciliation::handle_admin_request(['environment'=>'test','catalog_action'=>'purge','confirmation'=>'WRONG']);}catch(Throwable$e){$refused=true;}
check($refused,'exact confirmation required');check($before===$wpdb->get_results('SELECT * FROM wp_openfablab_animations'),'bad requests no write');
check(OpenFabLab_Reconciliation::handle_admin_request(['environment'=>'test','catalog_action'=>'purge','confirmation'=>'RESYNCHRONISER TEST'])['ok'],'admin catalogue purge');
foreach($private as$table=>$rows)check($rows===$wpdb->get_results('SELECT * FROM wp_openfablab_'.$table),'purge keeps '.$table);
check((int)animation(2,'production')['published']===1,'purge keeps Normal');
check(count(get_option('openfablab_res_catalog_audit'))===1,'audit no tokens or personal data');
check(snapshot([$p])['ok']===true,'next outbound sync repairs catalogue after purge');
check(!get_option('openfablab_res_refresh_test'),'refresh acknowledged only after snapshot');
echo "$tests reconciliation checks passed\n";
