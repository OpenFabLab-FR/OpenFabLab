<?php
if (!defined('ABSPATH')) { exit; }
require_once __DIR__.'/class-openfablab-i18n.php';

/** Public allowlists only. No accounts, private calendar, notes or booking tokens. */
final class OpenFabLab_Public {
    public static function valid_snapshot($data) {
        if (!is_array($data) || array_diff(array_keys($data),['version','timezone','coverage_start','coverage_end','calendar','machines','resource_label','history_start'])
            || ($data['version']??0)!==1 || !is_string($data['timezone']??null)
            || !in_array($data['timezone'],DateTimeZone::listIdentifiers(),true)) { return false; }
        if (isset($data['resource_label']) && !in_array($data['resource_label'],['resources','machines','equipment','rooms'],true)) { return false; }
        foreach (['coverage_start','coverage_end'] as $key) {
            if (!self::day($data[$key]??null)) { return false; }
        }
        if ($data['coverage_end']<=$data['coverage_start'] || strtotime($data['coverage_end'])-strtotime($data['coverage_start'])>140*86400) { return false; }
        if (array_key_exists('history_start',$data) && (!self::day($data['history_start']) || $data['history_start']<$data['coverage_start'] || $data['history_start']>=$data['coverage_end'])) { return false; }
        foreach (['calendar','machines'] as $section) {
            if (!isset($data[$section])) { continue; }
            if (!is_array($data[$section]) || count($data[$section])>500) { return false; }
            foreach ($data[$section] as $item) {
                if (!is_array($item)) { return false; }
                $allowed=$section==='machines'?['id','name','status','reason','return_estimate','category','category_key']:['id','kind','title','start','end','service_id','information_url','availability_state','signup_open_at','hide_before_opening','public_until','close_at','description','capacity','slots','attendance_average','history_eligible'];
                if (array_diff(array_keys($item),$allowed)) { return false; }
                foreach (($section==='machines'?['id','name','status','reason']:['id','kind','title','start','end']) as $key) {
                    if (!isset($item[$key]) || !is_string($item[$key]) || strlen($item[$key])>2000) { return false; }
                }
                if ($section==='machines') {
                    if (!in_array($item['status'],['operational','rental_available','maintenance','out_of_service','loaned','overdue'],true)) { return false; }
                    if (isset($item['return_estimate']) && !self::day($item['return_estimate'])) { return false; }
                    foreach (['category','category_key'] as $key) { if (isset($item[$key]) && (!is_string($item[$key]) || strlen($item[$key])>300)) { return false; } }
                } else {
                    if (array_key_exists('history_eligible',$item) && (!is_bool($item['history_eligible']) || !isset($data['history_start']))) { return false; }
                    if (($item['kind']??'')==='openlab' && array_diff(array_keys($item),['id','kind','title','start','end','attendance_average','history_eligible'])) { return false; }
                    if (!in_array($item['kind'],['animation','openlab'],true) || !self::instant($item['start']) || !self::instant($item['end']) || strtotime($item['end'])<=strtotime($item['start'])) { return false; }
                    if ($item['kind']==='animation') {
                        if (!is_int($item['service_id']??null) || $item['service_id']<=0 || !is_bool($item['hide_before_opening']??null)
                            || !self::instant($item['public_until']??null) || strtotime($item['public_until'])-strtotime($item['end'])!==86400
                            || !self::instant($item['close_at']??null) || strtotime($item['close_at'])>strtotime($item['start'])
                            || !is_string($item['signup_open_at']??null) || ($item['signup_open_at']!=='' && !self::instant($item['signup_open_at']))
                            || !in_array($item['availability_state']??null,['available','waiting','waiting_full','full','not_open','closed','ended'],true)) { return false; }
                        $url=$item['information_url']??'';
                        if (!is_string($url) || ($url!=='' && !self::public_url($url))) { return false; }
                        if (isset($item['description']) && (!is_string($item['description']) || strlen($item['description'])>40000)) { return false; }
                        if (isset($item['capacity']) && !self::capacity($item['capacity'])) { return false; }
                        if (isset($item['attendance_average'])) { return false; }
                        if (isset($item['slots'])) {
                            if (!is_array($item['slots']) || count($item['slots'])>500) { return false; }
                            foreach ($item['slots'] as $slot) {
                                if (!is_array($slot) || array_diff(array_keys($slot),['start','end','capacity','availability_state','close_at'])
                                    || !self::instant($slot['start']??null) || !self::instant($slot['end']??null)
                                    || strtotime($slot['end'])<=strtotime($slot['start']) || !self::capacity($slot['capacity']??null)
                                    || !self::instant($slot['close_at']??null) || strtotime($slot['close_at'])>strtotime($slot['start'])
                                    || !in_array($slot['availability_state']??null,['available','waiting','waiting_full','full','not_open','closed','ended'],true)) { return false; }
                            }
                        }
                    } elseif (isset($item['attendance_average'])) {
                        $average=$item['attendance_average'];
                        if (!is_array($average) || array_diff(array_keys($average),['users','visitors','since','until','method'])
                            || !is_int($average['users']??null) || $average['users']<5 || $average['users']>100000
                            || !is_int($average['visitors']??null) || $average['visitors']<0 || $average['visitors']>100000
                            || !self::day($average['since']??null) || !self::day($average['until']??null)
                            || $average['until']<$average['since'] || !in_array($average['method']??'', ['observed_same_weekday_hours_26w_v1','observed_same_weekday_hours_12m_v1'],true)) { return false; }
                    }
                }
            }
        }
        return true;
    }
    private static function capacity($value) { return is_int($value) && $value>=0 && $value<=100000; }
    private static function day($value) {
        if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2}$/D',$value)) { return false; }
        $date=DateTimeImmutable::createFromFormat('!Y-m-d',$value,new DateTimeZone('UTC'));
        return $date!==false && $date->format('Y-m-d')===$value;
    }
    private static function instant($value) {
        if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$/D',$value)) { return false; }
        $normalized=str_ends_with($value,'Z')?substr($value,0,-1).'+00:00':$value;
        $date=DateTimeImmutable::createFromFormat('!Y-m-d\TH:i:sP',$normalized);
        return $date!==false && $date->format('Y-m-d\TH:i:sP')===$normalized;
    }
    private static function public_url($url) {
        $parts=parse_url($url);$host=strtolower(rtrim($parts['host']??'','.'));
        return strlen($url)<=2048 && filter_var($url,FILTER_VALIDATE_URL) && in_array($parts['scheme']??'',['http','https'],true)
            && !isset($parts['user']) && !isset($parts['pass']) && $host!=='localhost' && !preg_match('/\.(local|localhost|lan|internal)$/D',$host)
            && (!filter_var($host,FILTER_VALIDATE_IP) || filter_var($host,FILTER_VALIDATE_IP,FILTER_FLAG_NO_PRIV_RANGE|FILTER_FLAG_NO_RES_RANGE));
    }
    public static function register() {
        foreach (['calendar','machines'] as $kind) {
            register_rest_route('openfablab/v1','/public/'.$kind,['methods'=>'GET','permission_callback'=>'__return_true',
                'callback'=>function($request) use ($kind) { return self::read($kind,(string)$request->get_param('environment')); }]);
        }
    }
    public static function register_shortcodes() {
        foreach (['calendar','machines'] as $kind) {
            add_shortcode('openfablab_'.$kind,function($attributes) use ($kind) { return self::shortcode($kind,$attributes); });
        }
        add_shortcode('openfablab_resources',function($attributes) { return self::shortcode('machines',$attributes); });
    }
    public static function read($kind,$env) {
        if (!in_array($env,['production','test'],true) || get_option('openfablab_public_'.$kind.'_enabled','0')!=='1') { return new WP_Error('openfablab_unavailable','Fonction non activée.',['status'=>404]); }
        $record=get_option('openfablab_public_snapshot_'.$env,[]);
        if (!is_array($record) || !self::valid_snapshot($record['data']??null)) { return new WP_Error('openfablab_waiting','En attente du premier échange.',['status'=>503]); }
        $data=$record['data'];$items=$data[$kind]??[];
        $zone=new DateTimeZone($data['timezone']);$today=new DateTimeImmutable('today',$zone);
        $first=self::month_before($today)->format('Y-m-d');
        $first=max($first,$data['history_start']??$data['coverage_start']);
        if ($kind==='calendar') {
            $now=time();$items=array_values(array_filter($items,function($item) use ($now,$first,$zone,$data) {
                $day=(new DateTimeImmutable($item['start']))->setTimezone($zone)->format('Y-m-d');
                if ($day<$first || $day>=$data['coverage_end']) { return false; }
                if ($item['kind']==='openlab') { return get_option('openfablab_calendar_openlab','1')==='1'; }
                $open=$item['signup_open_at']!==''?strtotime($item['signup_open_at']):0;
                $history=($item['history_eligible']??false)===true && isset($data['history_start']) && strtotime($item['end'])<=$now;
                return get_option('openfablab_calendar_animations','1')==='1' && ($now<strtotime($item['public_until']) || $history) && !($item['hide_before_opening'] && $open && $now<$open);
            }));
        }
        $response=new WP_REST_Response(['items'=>$items,'environment'=>$env,'timezone'=>$data['timezone'],
            'coverage_start'=>$data['coverage_start'],'coverage_end'=>$data['coverage_end'],'history_start'=>$first,'resource_label'=>$data['resource_label']??'resources',
            'updated_at'=>(int)$record['received_at'],'stale'=>time()-(int)$record['received_at']>900]);
        $response->header('Cache-Control','no-store');return $response;
    }
    public static function month_before($day) {
        $first=$day->modify('first day of last month');
        $number=min((int)$day->format('j'),(int)$first->format('t'));
        return $first->setDate((int)$first->format('Y'),(int)$first->format('n'),$number);
    }
    public static function assets() {
        // Same content-based cache keys as the existing reservation assets.
        // Replacing an unpublished candidate must not retain an older script.
        wp_enqueue_style('openfablab-public',plugins_url('assets/public.css',OPENFABLAB_RES_FILE),[],substr(hash_file('sha256',__DIR__.'/../assets/public.css'),0,12));
        wp_enqueue_script('openfablab-translations',plugins_url('assets/translations.js',OPENFABLAB_RES_FILE),[],substr(hash_file('sha256',__DIR__.'/../assets/translations.js'),0,12),true);
        wp_enqueue_script('openfablab-public',plugins_url('assets/public.js',OPENFABLAB_RES_FILE),['openfablab-translations'],substr(hash_file('sha256',__DIR__.'/../assets/public.js'),0,12),true);
        wp_add_inline_script('openfablab-public','window.OpenFabLabPublic='.wp_json_encode([
            'api'=>rest_url('openfablab/v1/public/'),'multilingual'=>get_option('openfablab_multilingual_enabled','0')==='1',
            'language'=>get_option('openfablab_public_language','fr'),'bookingPage'=>get_option('openfablab_booking_page',''),
            'showMachinesTitle'=>self::show_machines_title()]).';','before');
    }
    public static function initialize_display_settings() {
        // A regular upgrade with the existing schema does not reinstall. Its
        // absent option deliberately keeps the old visible title. A new install
        // records the hidden default before the schema marker is written.
        $existing=get_option('openfablab_res_schema_version',false)!==false
            || get_option('openfablab_public_machines_enabled',false)!==false;
        add_option('openfablab_public_machines_title',$existing?'1':'0','','no');
    }
    public static function show_machines_title() {
        return get_option('openfablab_public_machines_title','1')==='1';
    }
    public static function text($fr,$en) {
        $lang=get_option('openfablab_public_language','fr');
        if ($lang==='en') { return $en; }
        static $catalogs=[];
        if (in_array($lang,['de','es','fi'],true)) {
            if (!isset($catalogs[$lang])) { $catalogs[$lang]=json_decode(file_get_contents(__DIR__.'/../languages/'.$lang.'.json'),true) ?: []; }
            return $catalogs[$lang][$fr] ?? $fr;
        }
        return $fr;
    }
    public static function shortcode($kind,$attributes) {
        if (get_option('openfablab_public_'.$kind.'_enabled','0')!=='1') { return ''; }
        $attributes=shortcode_atts(['environment'=>'production','view'=>'week','category'=>''],$attributes,'openfablab_'.$kind);
        $env=in_array($attributes['environment'],['production','test'],true)?$attributes['environment']:'production';
        self::assets();
        $category=(string)$attributes['category'];
        if ($category!=='' && !preg_match('/^[a-zA-Z0-9_-]{1,100}$/D',$category)) { return ''; }
        return '<section class="openfablab-public" data-ofl-public="'.esc_attr($kind).'" data-environment="'.esc_attr($env).'" data-category="'.esc_attr($category).'" aria-live="polite"><p>'.self::text('Chargement…','Loading…').'</p></section>';
    }
    public static function settings() {
        if (!current_user_can('manage_options')) { return; }
        echo OpenFabLab_I18n::literal('<section class="ofl-card"><h2>Calendrier, machines et langues publiques</h2><form method="post" action="').esc_url(admin_url('admin-post.php')).'">';
        wp_nonce_field('openfablab_public_settings');echo '<input type="hidden" name="action" value="openfablab_public_settings">';
        foreach (['public_calendar_enabled'=>OpenFabLab_I18n::text('Activer le calendrier public'),'calendar_openlab'=>OpenFabLab_I18n::text('Afficher les OpenLab'),'calendar_animations'=>OpenFabLab_I18n::text('Afficher les animations'),'public_machines_enabled'=>OpenFabLab_I18n::text('Activer la liste publique des machines'),'multilingual_enabled'=>OpenFabLab_I18n::text('Permettre aux visiteurs de changer de langue')] as $key=>$label) {
            $default=in_array($key,['calendar_openlab','calendar_animations'],true)?'1':'0';
            echo '<label class="ofl-checkbox"><input name="'.esc_attr($key).'" value="1" type="checkbox" '.checked(get_option('openfablab_'.$key,$default),'1',false).'> '.esc_html($label).'</label>';
            if ($key==='public_machines_enabled') {
                echo '<label class="ofl-checkbox"><input name="public_machines_title" value="1" type="checkbox" aria-describedby="ofl-machines-title-help" '.checked(self::show_machines_title(),true,false).'> '.esc_html__(OpenFabLab_I18n::text('Afficher le titre de la liste des ressources'),'openfablab-reservations').'</label>';
                echo '<p class="ofl-help" id="ofl-machines-title-help">'.esc_html__(OpenFabLab_I18n::text('Utilise le nom public défini dans OpenFabLab (ex. : Machines). Vous pouvez aussi ajouter votre propre titre dans l’éditeur WordPress.'),'openfablab-reservations').'</p>';
            }
        }
        echo OpenFabLab_I18n::literal('<label>Langue par défaut<select name="language">');
        foreach (['fr'=>'Français','en'=>'English','de'=>'Deutsch','es'=>'Español','fi'=>'Suomi'] as $code=>$label) {
            echo '<option value="'.esc_attr($code).'" '.selected(get_option('openfablab_public_language','fr'),$code,false).'>'.esc_html($label).'</option>';
        }
        echo '</select></label>';
        echo OpenFabLab_I18n::literal('<label>Page de réservation, facultative<input type="url" name="booking_page" value="').esc_attr(get_option('openfablab_booking_page','')).'" placeholder="https://…"></label>';
        echo OpenFabLab_I18n::literal('<p><code>[openfablab_calendar environment="production" view="week"]</code></p><p><code>[openfablab_machines environment="production"]</code></p><p><button class="button button-primary">Enregistrer</button></p></form></section>');
    }
    public static function save_settings() {
        if (!current_user_can('manage_options')) { wp_die(OpenFabLab_I18n::text('Accès refusé.'),'',['response'=>403]); }
        check_admin_referer('openfablab_public_settings');
        foreach (['public_calendar_enabled','calendar_openlab','calendar_animations','public_machines_enabled','public_machines_title','multilingual_enabled'] as $key) { update_option('openfablab_'.$key,isset($_POST[$key])?'1':'0',false); }
        $lang=wp_unslash($_POST['language']??'fr');update_option('openfablab_public_language',in_array($lang,['fr','en','de','es','fi'],true)?$lang:'fr',false);
        $url=esc_url_raw(wp_unslash($_POST['booking_page']??''));
        if ($url==='' || self::public_url($url)) { update_option('openfablab_booking_page',$url,false); }
        wp_safe_redirect(admin_url('options-general.php?page=openfablab-reservations'));exit;
    }
}
