<?php
// Actual plugin entrypoint, modeled WP hooks + shortcode-block/frontend lifecycle.
// In-memory options only; no network, email, WordPress install or production data.
define('ABSPATH',__DIR__);$hooks=[];$shortcodes=[];$routes=[];$assets=[];$checks=0;
$options=['openfablab_res_schema_version'=>'2.8.2-relay3','openfablab_public_calendar_enabled'=>'1',
 'openfablab_public_machines_enabled'=>'1','openfablab_multilingual_enabled'=>'0','openfablab_public_language'=>'en',
 'openfablab_res_sync_secret'=>'FICTIONAL_PRESERVED_SECRET'];
function check($ok,$label){if(!$ok)throw new RuntimeException($label);$GLOBALS['checks']++;}
function add_action($name,$callback,...$args){$GLOBALS['hooks'][$name][]=$callback;}
function add_filter($name,$callback,...$args){add_action($name,$callback);}
function do_action($name){foreach($GLOBALS['hooks'][$name]??[] as $callback)$callback();}
function register_activation_hook(...$x){}function register_deactivation_hook(...$x){}
function plugin_dir_path($path){return dirname($path).'/';}
function get_option($key,$default=''){return $GLOBALS['options'][$key]??$default;}
function add_shortcode($name,$handler){$GLOBALS['shortcodes'][$name]=$handler;}
function shortcode_atts($defaults,$atts,...$rest){return array_merge($defaults,$atts);}
function register_rest_route($namespace,$route,$data){$GLOBALS['routes'][$route]=$data;}
function plugins_url($path,...$x){return 'https://example.invalid/plugin/'.$path;}
function rest_url($path){return 'https://example.invalid/wp-json/'.$path;}
function esc_url_raw($s){return $s;}function esc_attr($s){return htmlspecialchars((string)$s,ENT_QUOTES);}
function wp_generate_password(...$x){return 'FICTIVE1';}function wp_json_encode($x){return json_encode($x);}
function wp_enqueue_style(...$x){$GLOBALS['assets'][]=$x;}function wp_enqueue_script(...$x){$GLOBALS['assets'][]=$x;}
function wp_add_inline_script(...$x){$GLOBALS['assets'][]=$x;}
require dirname(__DIR__).'/wordpress/openfablab-reservations/openfablab-reservations.php';
$before=$options;
do_action('plugins_loaded');do_action('init');
check(OPENFABLAB_RES_VERSION==='2.15.3','actual version metadata 2.15.3');
check(count($shortcodes)===4,'three original shortcodes and resource alias present on ordinary frontend');
check(!$routes,'frontend does not initialize REST routes');
foreach(['reservations','calendar','machines'] as $kind){
 $name='openfablab_'.$kind;check(isset($shortcodes[$name]),'shortcode registered '.$kind);
 $html=$shortcodes[$name](['environment'=>'production','view'=>'week']);
 check(str_contains($html,'data-environment="production"'),'production output '.$kind);
 check(!str_contains($html,'['.$name),'no literal shortcode '.$kind);
 // Gutenberg Shortcode blocks pass the contained shortcode through its handler.
 $block='<!-- wp:shortcode -->['.$name.' environment="production"]<!-- /wp:shortcode -->';
 $rendered=preg_replace_callback('/\[(openfablab_\w+) environment="production"\]/',fn($m)=>$shortcodes[$m[1]](['environment'=>'production']),$block);
 check(str_contains($rendered,'<section')&&!str_contains($rendered,'['.$name),'modeled Gutenberg shortcode block '.$kind);
 check(!str_contains($rendered,'FICTIONAL_PRESERVED_SECRET'),'secret not rendered '.$kind);
}
check($options===$before,'all existing options preserved on plugin load/frontend');
$shortcodes_before=array_keys($shortcodes);do_action('rest_api_init');
check(array_keys($shortcodes)===$shortcodes_before,'REST does not register or replace shortcodes');
check(isset($routes['/public/calendar'])&&isset($routes['/public/machines']),'REST routes initialized in their own lifecycle');
$configs=[];foreach($assets as $entry){if(is_string($entry[1]??null)&&str_starts_with($entry[1],'window.OpenFabLabPublic='))$configs[]=json_decode(substr($entry[1],strlen('window.OpenFabLabPublic='),-1),true);}
check(count($configs)===6,'same configuration emitted by three frontend and three block renders');
foreach($configs as $config){check($config['multilingual']===false,'existing multilingual option controls public widget');check($config['language']==='en','configured default language kept');}
echo $checks." frontend/init/Gutenberg-model checks passed\n";
