<?php
if (!defined('ABSPATH')) { exit; }

function ofl_account_cookie() {
    $cookie=$_COOKIE['__Host-ofl-account']??'';
    return is_string($cookie) && preg_match('/^[a-f0-9]{64}$/D',$cookie) ? $cookie : '';
}
function ofl_account_binding($env) {
    if (!ofl_account_cookie() || !in_array($env,['production','test'],true)) { throw new RuntimeException('Session expirée.'); }
    return hash_hmac('sha256','account/v1|'.$env.'|'.ofl_account_cookie(),wp_salt('auth'));
}
function ofl_account_page($env) {
    if (get_transient('ofl_portal_ready_'.$env)!=='1') { return ''; }
    $id=(int)get_option('ofl_account_page_'.$env,0);
    if (!$id || get_post_status($id)!=='publish' || post_password_required($id)) { return ''; }
    return get_permalink($id);
}
function ofl_account_languages() {
    static $catalogs;
    if (!isset($catalogs)) { $catalogs=json_decode(file_get_contents(OPENFABLAB_RES_PATH.'languages/account.json'),true); }
    return $catalogs;
}
add_action('save_post_page',function($id,$page) {
    if (wp_is_post_revision($id) || !current_user_can('edit_page',$id)) { return; }
    foreach (['test','production'] as $env) {
        if (preg_match('/\[openfablab_account\s+environment=["\']'. $env .'["\']\s*\/?\]/',$page->post_content)
            && $page->post_status==='publish') { update_option('ofl_account_page_'.$env,$id,false); }
        elseif ((int)get_option('ofl_account_page_'.$env,0)===$id) { delete_option('ofl_account_page_'.$env); }
    }
},10,2);
add_action('template_redirect',function() {
    $page=get_queried_object();
    if ($page instanceof WP_Post && has_shortcode($page->post_content,'openfablab_account')) {
        if (!defined('DONOTCACHEPAGE')) { define('DONOTCACHEPAGE',true); }
        nocache_headers(); header('Cache-Control: private, no-store, max-age=0');
        header('Referrer-Policy: no-referrer');header('X-Robots-Tag: noindex, nofollow');
    }
});
add_shortcode('openfablab_account',function($atts) {
    $atts=shortcode_atts(['environment'=>'test'],$atts,'openfablab_account');
    if (!in_array($atts['environment'],['production','test'],true)) { return ''; }
    OpenFabLab_Public::assets();
    $translations=ofl_account_languages();
    wp_add_inline_script('openfablab-public','window.OpenFabLabAccountLanguages='.wp_json_encode($translations,JSON_HEX_TAG|JSON_HEX_AMP|JSON_HEX_QUOT|JSON_HEX_APOS).';','before');
    foreach (['css','js'] as $ext) {
        $file='assets/account.'.$ext;$url=plugins_url($file,OPENFABLAB_RES_FILE);
        $v=substr(hash_file('sha256',OPENFABLAB_RES_PATH.$file),0,12);
        if ($ext==='css') { wp_enqueue_style('ofl-account',$url,[],$v); }
        else { wp_enqueue_script('ofl-account',$url,['openfablab-public'],$v,true); }
    }
    // Cacheable HTML contains no contact, users, session value or CSRF token.
    $privacy=get_option('openfablab_res_privacy_url','') ?: get_privacy_policy_url();
    return '<section class="openfablab-public ofl-account" data-env="'.esc_attr($atts['environment']).'" data-api="'.esc_url(rest_url('openfablab/v1/public/')).'" data-privacy="'.esc_url($privacy).'" aria-label="Mon compte"><header class="ofl-module-toolbar"><h2>Mon compte</h2></header><div class="ofl-account-notice" role="status" aria-live="polite"></div><div class="ofl-account-body"><p>Consultez vos informations, votre famille et vos réservations.</p></div><noscript>Activez JavaScript ou contactez l’équipe du FabLab.</noscript></section>';
});
add_action('rest_api_init',function() {
    register_rest_route('openfablab/v1','/public/account',['methods'=>'POST','permission_callback'=>['OpenFabLab_Relay','permission'],
        'callback'=>function($request) {
            $data=$request->get_json_params();$env=$data['environment']??'';$op=$data['op']??'';
            if (!in_array($env,['production','test'],true) || get_transient('ofl_portal_ready_'.$env)!=='1') {
                return new WP_Error('ofl_portal_off','Espace usager indisponible. Les réservations habituelles restent accessibles.',['status'=>503]);
            }
            if (!ofl_account_cookie() || !in_array($op,['options','bootstrap','overview','qr','login','signup','recover','confirm','logout','child','phone','email','reserve','cancel','accept_offer','decline_offer'],true)) {
                return new WP_Error('ofl_invalid','Demande invalide ou session expirée.',['status'=>400]);
            }
            // Neither IP buckets nor authenticated browser identity are accepted from the browser.
            $data['browser']=ofl_account_binding($env);
            $data['client_bucket']=hash_hmac('sha256',(string)($_SERVER['REMOTE_ADDR']??''),wp_salt('auth'));
            return OpenFabLab_Relay::enqueue('account',$data);
        }]);
});
