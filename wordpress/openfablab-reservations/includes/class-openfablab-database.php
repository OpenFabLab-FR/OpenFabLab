<?php
if (!defined('ABSPATH')) { exit; }

/** Only anti-replay nonces and the two durable transport tables are managed. */
final class OpenFabLab_Database {
    public static function table($name) {
        global $wpdb;
        if (!in_array($name,['nonces','relay_catalogues','relay_actions'],true)) {
            throw new InvalidArgumentException('Table inconnue');
        }
        return $wpdb->prefix.'openfablab_'.$name;
    }
    public static function install() {
        global $wpdb;
        require_once ABSPATH.'wp-admin/includes/upgrade.php';
        $collation=$wpdb->get_charset_collate();
        $nonces=self::table('nonces');
        dbDelta("CREATE TABLE $nonces (
            nonce_hash char(64) NOT NULL,
            expires_at datetime NOT NULL,
            PRIMARY KEY  (nonce_hash),
            KEY expires_at (expires_at)
        ) ENGINE=InnoDB $collation;");
        OpenFabLab_Relay::install($collation);
        self::assert_transactional();
        self::retire_empty_storage();
        wp_clear_scheduled_hook('openfablab_res_maintenance');
        update_option('openfablab_res_schema_version',OPENFABLAB_RES_SCHEMA_VERSION,false);
    }
    public static function assert_transactional() {
        global $wpdb;
        foreach (['nonces','relay_catalogues','relay_actions'] as $name) {
            $table=self::table($name);
            $engine=$wpdb->get_var($wpdb->prepare(
                'SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s',$table));
            if (strtoupper((string)$engine)!=='INNODB') { throw new RuntimeException('Stockage transactionnel indisponible.'); }
        }
    }
    public static function connection_lock() {
        global $wpdb;
        $name='ofl_connection_'.substr(hash('sha256',$wpdb->prefix),0,32);
        if ((string)$wpdb->get_var($wpdb->prepare('SELECT GET_LOCK(%s,5)',$name))!=='1') {
            throw new RuntimeException('Connexion occupée.');
        }
    }
    public static function connection_unlock() {
        global $wpdb;
        $name='ofl_connection_'.substr(hash('sha256',$wpdb->prefix),0,32);
        $wpdb->get_var($wpdb->prepare('SELECT RELEASE_LOCK(%s)',$name));
    }
    private static function quoted($table) { return chr(96).str_replace(chr(96),chr(96).chr(96),$table).chr(96); }
    private static function retire_empty_storage() {
        global $wpdb;
        $tables=[];
        foreach (['tokens','events','reservations','directory','animations'] as $name) {
            $table=$wpdb->prefix.'openfablab_'.$name;
            if ($wpdb->get_var($wpdb->prepare(
                'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s',$table))) {
                $tables[]=$table;
            }
        }
        $state='absent';
        if ($tables) {
            $quoted=array_map([__CLASS__,'quoted'],$tables);
            $locked=false;
            try {
                if ($wpdb->query('LOCK TABLES '.implode(',',array_map(fn($name)=>$name.' WRITE',$quoted)))===false) {
                    throw new RuntimeException();
                }
                $locked=true;
                foreach ($quoted as $name) {
                    $count=$wpdb->get_var('SELECT COUNT(*) FROM '.$name);
                    if ($wpdb->last_error || $count===null) { throw new RuntimeException(); }
                    if ((int)$count!==0) { $state='retained'; break; }
                }
                if ($state!=='retained') {
                    if ($wpdb->query('DROP TABLE '.implode(',',$quoted))===false) { throw new RuntimeException(); }
                    $state='removed_empty';
                }
            } catch (Throwable $error) { $state='retained_review'; }
            finally { if ($locked) { $wpdb->query('UNLOCK TABLES'); } }
        }
        // Never erase nonempty historical storage, nor any OpenFabLab data.
        update_option('openfablab_res_retired_storage',$state,false);
        if (in_array($state,['absent','removed_empty'],true)) {
            foreach (['core_url','last_sync','from_name','from_email','reply_to','test_prefix','email_settings'] as $key) {
                delete_option('openfablab_res_'.$key);
            }
            foreach (['production','test'] as $env) { delete_option('openfablab_res_attempt_'.$env); }
        }
    }
}
