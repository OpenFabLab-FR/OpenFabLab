<?php
// Current distributed plugin only; no historical engine is loaded.
define('ABSPATH',__DIR__);define('OPENFABLAB_RES_VERSION','2.8.2');
define('OPENFABLAB_RES_SCHEMA_VERSION','2.8.2-relay3');
define('OPENFABLAB_RES_PATH',dirname(__DIR__).'/wordpress/openfablab-reservations/');
define('OPENFABLAB_RES_FILE',OPENFABLAB_RES_PATH.'openfablab-reservations.php');
$checks=0;$options=['openfablab_res_sync_secret'=>str_repeat('f',64)];$routes=[];$assets=[];
function check($ok,$label){global $checks;if(!$ok)throw new Exception($label);$checks++;}
function get_option($key,$default=''){global $options;return $options[$key]??$default;}
function update_option($key,$value,$autoload=false){global $options;$options[$key]=$value;return true;}
function is_ssl(){return true;}
function esc_html($x){return htmlspecialchars((string)$x,ENT_QUOTES);}
function esc_attr($x){return esc_html($x);}
function esc_url($x){return esc_html($x);}
function esc_url_raw($x){return $x;}
function wp_unslash($x){return $x;}
function current_user_can($x){return true;}
function wp_nonce_field($x){echo '<input name="_wpnonce" value="fictional-nonce">';}
function checked($a,$b,$echo=false){return $a===$b?'checked':'';}
function admin_url($x){return 'https://example.invalid/wp-admin/'.$x;}
function plugins_url($x,$file){return 'https://example.invalid/plugin/'.$x;}
function human_time_diff($a,$b){return (string)max(0,$b-$a).' s';}
function wp_date($format,$stamp){return gmdate($format,$stamp);}
function register_rest_route($namespace,$route,$data){global $routes;$routes[$route]=$data;}
function wp_enqueue_style(...$args){global $assets;$assets[]=$args;}
function wp_enqueue_script(...$args){global $assets;$assets[]=$args;}
function is_wp_error($x){return $x instanceof WP_Error;}
class WP_Error {public $code,$message,$data;function __construct($c,$m,$d=[]){$this->code=$c;$this->message=$m;$this->data=$d;}}
class WP_REST_Request {
    public $body='{}',$headers=[],$params=[];
    function get_body(){return $this->body;}function get_header($name){return $this->headers[$name]??'';}
    function get_method(){return 'POST';}function get_route(){return '/openfablab/v1/sync/capabilities';}
    function get_param($key){return $this->params[$key]??'';}
}
class WPDB {
    public $prefix='wp_',$last_error='',$nonce=true;
    function prepare($sql,...$args){return $sql.' /* '.json_encode($args).' */';}
    function query($sql){if(str_starts_with($sql,'INSERT IGNORE'))return $this->nonce?1:0;return 1;}
    function get_var($sql){if(str_contains($sql,'ENGINE'))return 'InnoDB';if(str_contains($sql,'GET_LOCK'))return 1;if(str_contains($sql,'catalogue_json'))return '[]';return 0;}
    function get_row($sql){return (object)['pending'=>0,'processing'=>0,'failed'=>0,'retrying'=>0];}
}
$wpdb=new WPDB;
foreach(['database','relay','api','admin']as$name)require OPENFABLAB_RES_PATH.'includes/class-openfablab-'.$name.'.php';
OpenFabLab_API::register();
foreach(['/sync/snapshot','/sync/animations','/sync/directory','/sync/events','/sync/commands','/heartbeat']as$route)check(!isset($routes[$route]),'obsolete route absent '.$route);
foreach(['Bookings','Slots','Emails','Reconciliation','Legacy_Reset','Test_Maintenance','Family_Gateway']as$name)check(!class_exists('OpenFabLab_'.$name),'obsolete class absent '.$name);
foreach(['animations','reservations','directory','events','tokens']as$name){try{OpenFabLab_Database::table($name);check(false,'old table exposed');}catch(InvalidArgumentException $error){check(true,'old table not managed');}}
foreach(['nonces','relay_catalogues','relay_actions']as$name)check(OpenFabLab_Database::table($name)==='wp_openfablab_'.$name,'only transport table');
$request=new WP_REST_Request;$request->body='{"environment":"production"}';
$caps=OpenFabLab_API::capabilities($request);check($caps['transport_only_v1']===true&&$caps['relay_revision']===3,'transport revision');check($caps['relay_state']['environment']==='production','scoped metadata');
$request->headers=['x-openfablab-timestamp'=>(string)time(),'x-openfablab-nonce'=>str_repeat('a',24)];
$canonical=$request->headers['x-openfablab-timestamp']."\n".$request->headers['x-openfablab-nonce']."\nPOST\n".$request->get_route()."\n".hash('sha256',$request->body);
$request->headers['x-openfablab-signature']=hash_hmac('sha256',$canonical,$options['openfablab_res_sync_secret']);
check(OpenFabLab_API::private_permission($request)===true,'valid signed private request');
$wpdb->nonce=false;check(OpenFabLab_API::private_permission($request)->code==='openfablab_replay','nonce replay refused');$wpdb->nonce=true;
foreach(['x-openfablab-signature'=>str_repeat('0',64),'x-openfablab-timestamp'=>(string)(time()-301),'x-openfablab-nonce'=>'bad']as$key=>$value){$old=$request->headers[$key];$request->headers[$key]=$value;check(OpenFabLab_API::private_permission($request)->code==='openfablab_forbidden','invalid signed request');$request->headers[$key]=$old;}
$request->body=str_repeat('x',32769);check(OpenFabLab_API::public_reserve($request)->data['status']===400,'oversize deposit refused');
$request->body='not json';check(OpenFabLab_API::public_verify($request)->data['status']===400,'malformed deposit refused');
$state=['catalogue_at'=>0,'polled_at'=>0];check(OpenFabLab_Admin::status($state,true,true,true)[0]==='waiting','first contact honestly pending');
check(OpenFabLab_Admin::status($state,false,true,true)[0]==='action','missing secret');check(OpenFabLab_Admin::status($state,true,false,true)[0]==='action','missing HTTPS');check(OpenFabLab_Admin::status($state,true,true,false)[0]==='error','storage error');
$state=['catalogue_at'=>time(),'polled_at'=>time()];check(OpenFabLab_Admin::status($state,true,true,true)[0]==='connected','fresh catalogue and poll connected');$state['polled_at']=time()-121;check(OpenFabLab_Admin::status($state,true,true,true)[0]==='action','stale poll needs action');
$_SERVER['REQUEST_METHOD']='GET';ob_start();OpenFabLab_Admin::render();$html=ob_get_clean();
check(!str_contains($html,$options['openfablab_res_sync_secret']),'secret never rendered');
foreach(['Connexion à OpenFabLab','Normal','Environnement Test','Diagnostic avancé','Sécurité de la connexion','Page de réservation','Régénérer et télécharger la clé']as$text)check(str_contains($html,$text),'admin user-facing section');
check(substr_count($html,'<details')>=4,'secondary content collapsible');check(!str_contains($html,'Adresse publique HTTPS'),'no core URL input');check(!str_contains($html,'Un contact signé'),'no old diagnostic wall');
OpenFabLab_Admin::assets('other');check(!$assets,'admin assets scoped');OpenFabLab_Admin::assets('settings_page_openfablab-reservations');check(count($assets)===2,'scoped CSS and JS');
foreach($routes as$route=>$data)check(isset($data['permission_callback']),'every actual route has permission');
echo $checks." transport/admin PHP checks passed\n";
