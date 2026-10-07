<?php
if (!defined('ABSPATH')) { exit; }

/** Transport only. Capacity, identities and booking decisions belong to OpenFabLab. */
final class OpenFabLab_API {
    public static function register() {
        OpenFabLab_Relay::register();
        register_rest_route('openfablab/v1', '/sync/capabilities', [
            'methods'=>'POST', 'callback'=>[__CLASS__,'capabilities'],
            'permission_callback'=>[__CLASS__,'private_permission'],
        ]);
        register_rest_route('openfablab/v1', '/public/animations', [
            'methods'=>'GET', 'callback'=>[__CLASS__,'public_animations'],
            'permission_callback'=>'__return_true',
        ]);
        foreach (['verify','contact','reserve','guest'] as $name) {
            register_rest_route('openfablab/v1', '/public/'.$name, [
                'methods'=>'POST', 'callback'=>[__CLASS__,'public_'.$name],
                'permission_callback'=>['OpenFabLab_Relay','permission'],
            ]);
        }
    }
    public static function capabilities(WP_REST_Request $request) {
        $value = ['ok'=>true, 'animation_slots_v1'=>true, 'custom_categories_v1'=>true,
            'catalog_snapshot_v1'=>false, 'family_gateway_v1'=>false,
            'protocol_version'=>4, 'outbound_actions_v1'=>true, 'transport_only_v1'=>true,
            'relay_revision'=>3, 'plugin_version'=>OPENFABLAB_RES_VERSION];
        $body=json_decode($request->get_body(),true);
        if (is_array($body) && in_array($body['environment'] ?? '',['production','test'],true)) {
            $value['relay_state']=OpenFabLab_Relay::state($body['environment']);
        }
        return $value;
    }
    public static function private_permission(WP_REST_Request $request) {
        $secret=(string)get_option('openfablab_res_sync_secret','');
        $stamp=$request->get_header('x-openfablab-timestamp');
        $nonce=$request->get_header('x-openfablab-nonce');
        $signature=$request->get_header('x-openfablab-signature');
        if (!$secret || !is_ssl() || !ctype_digit((string)$stamp) || abs(time()-(int)$stamp)>300
            || !preg_match('/^[A-Za-z0-9_-]{20,80}$/D',(string)$nonce)
            || !preg_match('/^[a-f0-9]{64}$/D',(string)$signature)) {
            return new WP_Error('openfablab_forbidden','Synchronisation refusée.',['status'=>403]);
        }
        $canonical=$stamp."\n".$nonce."\n".$request->get_method()."\n".$request->get_route()."\n".hash('sha256',$request->get_body());
        if (!hash_equals(hash_hmac('sha256',$canonical,$secret),$signature)) {
            return new WP_Error('openfablab_forbidden','Synchronisation refusée.',['status'=>403]);
        }
        global $wpdb;
        $inserted=$wpdb->query($wpdb->prepare(
            'INSERT IGNORE INTO '.OpenFabLab_Database::table('nonces').' (nonce_hash,expires_at) VALUES (%s,%s)',
            hash_hmac('sha256',$nonce,$secret),gmdate('Y-m-d H:i:s',time()+600)));
        if ($inserted!==1) { return new WP_Error('openfablab_replay','Requête déjà traitée.',['status'=>409]); }
        OpenFabLab_Relay::authenticated($request,$nonce);
        return true;
    }
    public static function public_animations(WP_REST_Request $request) {
        return OpenFabLab_Relay::public_catalogue((string)$request->get_param('environment'));
    }
    private static function deposit(WP_REST_Request $request,$type) {
        $body=$request->get_body();
        if (strlen($body)>32768) { return new WP_Error('openfablab_relay','Demande trop volumineuse.',['status'=>400]); }
        $data=json_decode($body,true);
        if (!is_array($data)) { return new WP_Error('openfablab_relay','Demande invalide.',['status'=>400]); }
        return OpenFabLab_Relay::enqueue($type,$data);
    }
    public static function public_verify(WP_REST_Request $request) { return self::deposit($request,'identify'); }
    public static function public_contact(WP_REST_Request $request) { return self::deposit($request,'contact'); }
    public static function public_reserve(WP_REST_Request $request) { return self::deposit($request,'reserve'); }
    public static function public_guest(WP_REST_Request $request) { return self::deposit($request,'guest'); }
}
