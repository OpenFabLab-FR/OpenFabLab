<?php
// Current public projections only, in-memory WP options, no HTTP/mail/database.
define('ABSPATH',__DIR__);define('OPENFABLAB_RES_VERSION','2.14.0');
define('OPENFABLAB_RES_FILE',dirname(__DIR__).'/wordpress/openfablab-reservations/openfablab-reservations.php');
$options=[];$routes=[];$shortcodes=[];$assets=[];$checks=0;
function check($ok,$why){if(!$ok)throw new RuntimeException($why);$GLOBALS['checks']++;}
function get_option($k,$d=''){return $GLOBALS['options'][$k]??$d;}
function update_option($k,$v,...$rest){$GLOBALS['options'][$k]=$v;return true;}
function register_rest_route($ns,$route,$data){$GLOBALS['routes'][$route]=$data;}
function add_shortcode($name,$handler){$GLOBALS['shortcodes'][$name]=$handler;}
function shortcode_atts($defaults,$value,...$rest){return array_merge($defaults,$value);}
function esc_attr($s){return htmlspecialchars($s,ENT_QUOTES);}
function wp_json_encode($s){return json_encode($s);}
function wp_enqueue_style(...$args){$GLOBALS['assets'][]=$args;}
function wp_enqueue_script(...$args){$GLOBALS['assets'][]=$args;}
function wp_add_inline_script(...$args){$GLOBALS['assets'][]=$args;}
function plugins_url($s,...$rest){return 'https://example.invalid/plugin/'.$s;}
function rest_url($s){return 'https://example.invalid/wp-json/'.$s;}
class WP_Error {function __construct(public $code,public $message,public $data=[]) {}}
class WP_REST_Response {public $headers=[];function __construct(public $data){}function header($k,$v){$this->headers[$k]=$v;}}
require dirname(__DIR__).'/wordpress/openfablab-reservations/includes/class-openfablab-public.php';
$snapshot=['version'=>1,'timezone'=>'Europe/Paris','coverage_start'=>'2026-11-01','coverage_end'=>'2027-01-15','machines'=>[
 ['id'=>'fictional-machine','name'=>'Laser Exemple','status'=>'maintenance','reason'=>'Public only','return_estimate'=>null]],'calendar'=>[
 ['id'=>'openlab-fictional','kind'=>'openlab','title'=>'OpenLab Exemple','start'=>'2026-12-01T10:00:00+01:00','end'=>'2026-12-01T12:00:00+01:00']]];
check(OpenFabLab_Public::valid_snapshot($snapshot),'explicit projection accepted');
foreach(['2026-02-30','2026-13-01','invalid'] as $day){$bad=$snapshot;$bad['coverage_start']=$day;check(!OpenFabLab_Public::valid_snapshot($bad),'invalid calendar day rejected');$bad=$snapshot;$bad['machines'][0]['return_estimate']=$day;check(!OpenFabLab_Public::valid_snapshot($bad),'invalid return day rejected');}
$bad=$snapshot;$bad['calendar'][0]['start']='2026-02-30T10:00:00+01:00';check(!OpenFabLab_Public::valid_snapshot($bad),'invalid instant not normalized silently');
$unicode=$snapshot;$unicode['machines'][0]['reason']=str_repeat('é',500);check(OpenFabLab_Public::valid_snapshot($unicode),'500-character public reason accepted');
foreach(['contact_email','manage_token','actor','description','private_note','users','participants','billing'] as $key){$bad=$snapshot;$bad['machines'][0][$key]='SENSITIVE_FAKE';check(!OpenFabLab_Public::valid_snapshot($bad),'private field rejected '.$key);}
foreach(['notes','sessions','family','secret'] as $key){$bad=$snapshot;$bad[$key]=[];check(!OpenFabLab_Public::valid_snapshot($bad),'top-level field rejected '.$key);}
foreach(['internal-state','',false] as $state){$bad=$snapshot;$bad['machines'][0]['status']=$state;check(!OpenFabLab_Public::valid_snapshot($bad),'invalid machine state refused');}
$bad=$snapshot;$bad['calendar'][0]['end']=$bad['calendar'][0]['start'];check(!OpenFabLab_Public::valid_snapshot($bad),'non-positive interval refused');
$bad=$snapshot;$bad['timezone']='Fake/Zone';check(!OpenFabLab_Public::valid_snapshot($bad),'unknown timezone refused');
foreach(['calendar','machines'] as $kind){
 check(OpenFabLab_Public::shortcode($kind,[])==='','optional shortcode disabled by default '.$kind);
 check(OpenFabLab_Public::read($kind,'production') instanceof WP_Error,'optional endpoint disabled by default '.$kind);
 $options['openfablab_public_'.$kind.'_enabled']='1';
 check(str_contains(OpenFabLab_Public::shortcode($kind,['environment'=>'production']),'data-environment="production"'),'independent shortcode enabled '.$kind);
 check(OpenFabLab_Public::read($kind,'test') instanceof WP_Error,'no Normal/Test bleed '.$kind);
 $options['openfablab_public_snapshot_production']=['data'=>$snapshot,'received_at'=>time()-901];
 $response=OpenFabLab_Public::read($kind,'production');check($response instanceof WP_REST_Response,'published projection available '.$kind);
 check($response->data['stale']===true,'stale warning honest '.$kind);
 check($response->headers['Cache-Control']==='no-store','no stale browser caching '.$kind);
 check(!str_contains(json_encode($response->data),'SENSITIVE_FAKE'),'no internal data '.$kind);
 $options['openfablab_public_snapshot_production']['received_at']=time();check(!OpenFabLab_Public::read($kind,'production')->data['stale'],'fresh received timestamp '.$kind);
}
check(get_option('openfablab_multilingual_enabled','0')==='0','multilingual disabled by default');
check(OpenFabLab_Public::text('Bonjour','Hello')==='Bonjour','default French');$options['openfablab_public_language']='en';check(OpenFabLab_Public::text('Bonjour','Hello')==='Hello','default English independent');
OpenFabLab_Public::register();check(count($routes)===2&&count($shortcodes)===0,'REST routes only');OpenFabLab_Public::register_shortcodes();check(count($shortcodes)===3,'frontend shortcodes and compatible resources alias registered independently');
$future=time()+7200;$animation=['id'=>'animation-1','kind'=>'animation','title'=>'Fictional','service_id'=>1,'start'=>gmdate('Y-m-d\TH:i:s\Z',$future),'end'=>gmdate('Y-m-d\TH:i:s\Z',$future+3600),'signup_open_at'=>gmdate('Y-m-d\TH:i:s\Z',$future-3600),'hide_before_opening'=>true,'public_until'=>gmdate('Y-m-d\TH:i:s\Z',$future+90000),'information_url'=>'https://example.invalid/activity','availability_state'=>'not_open'];
$animation['close_at']=gmdate('Y-m-d\TH:i:s\Z',$future-900);
$snapshot['calendar']=[$animation];check(OpenFabLab_Public::valid_snapshot($snapshot),'publication projection valid');
$options['openfablab_public_snapshot_production']=['data'=>$snapshot,'received_at'=>time()];check(OpenFabLab_Public::read('calendar','production')->data['items']===[],'hidden before opening');
$snapshot['calendar'][0]['hide_before_opening']=false;$options['openfablab_public_snapshot_production']['data']=$snapshot;check(count(OpenFabLab_Public::read('calendar','production')->data['items'])===1,'explicit visible before opening');
foreach(['https://localhost/a','https://127.0.0.1/a','https://'.implode('.',[192,168,1,1]).'/a','https://user:password@example.invalid/a'] as $url){$bad=$snapshot;$bad['calendar'][0]['information_url']=$url;check(!OpenFabLab_Public::valid_snapshot($bad),'unsafe public URL rejected');}
echo $checks." v214 public PHP checks passed\n";
