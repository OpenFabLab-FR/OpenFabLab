<?php
if (!defined('ABSPATH')) { exit; }

final class OpenFabLab_Database {
    public static function table($name) {
        global $wpdb;
        $allowed = ['animations', 'reservations', 'directory', 'events', 'tokens', 'nonces'];
        if (!in_array($name, $allowed, true)) { throw new InvalidArgumentException('Table inconnue'); }
        return $wpdb->prefix . 'openfablab_' . $name;
    }

    public static function install() {
        global $wpdb;
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        $collation = $wpdb->get_charset_collate();
        $animations = self::table('animations');
        $reservations = self::table('reservations');
        $directory = self::table('directory');
        $events = self::table('events');
        $tokens = self::table('tokens');
        $nonces = self::table('nonces');
        $queries = [];
        $queries[] = "CREATE TABLE $animations (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            environment varchar(12) NOT NULL,
            service_id bigint(20) unsigned NOT NULL,
            title varchar(160) NOT NULL,
            description text NOT NULL,
            starts_at datetime NOT NULL,
            ends_at datetime NOT NULL,
            timezone varchar(80) NOT NULL,
            capacity int(11) NOT NULL,
            booking_mode varchar(12) NOT NULL DEFAULT 'whole',
            slot_duration_minutes int(11) NOT NULL DEFAULT 20,
            slot_gap_minutes int(11) NOT NULL DEFAULT 0,
            slot_capacity int(11) NOT NULL DEFAULT 1,
            slots_json longtext DEFAULT NULL,
            minimum_age int(11) NOT NULL,
            audience varchar(20) NOT NULL,
            accompaniment_under_age int(11) NOT NULL,
            waitlist_enabled tinyint(1) NOT NULL,
            close_minutes int(11) NOT NULL,
            signup_open_at datetime DEFAULT NULL,
            reminder_one_hours int(11) DEFAULT NULL,
            reminder_two_hours int(11) DEFAULT NULL,
            offer_hours int(11) NOT NULL DEFAULT 12,
            last_offer_hours int(11) NOT NULL DEFAULT 24,
            published tinyint(1) NOT NULL DEFAULT 0,
            updated_at datetime NOT NULL,
            PRIMARY KEY  (id),
            UNIQUE KEY environment_service (environment,service_id),
            KEY starts_at (starts_at)
        ) ENGINE=InnoDB $collation;";
        $queries[] = "CREATE TABLE $reservations (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            uuid char(36) NOT NULL,
            environment varchar(12) NOT NULL,
            animation_id bigint(20) unsigned NOT NULL,
            first_name varchar(80) NOT NULL,
            last_name varchar(80) NOT NULL,
            birth_year int(11) DEFAULT NULL,
            email varchar(254) NOT NULL,
            phone varchar(40) NOT NULL,
            status varchar(24) NOT NULL,
            link_status varchar(24) NOT NULL,
            public_id varchar(4) DEFAULT NULL,
            group_uuid char(36) DEFAULT NULL,
            slot_uuid char(36) DEFAULT NULL,
            identity_key char(64) NOT NULL,
            is_present tinyint(1) DEFAULT NULL,
            source varchar(24) NOT NULL DEFAULT 'online',
            reminder_one_sent_at datetime DEFAULT NULL,
            reminder_two_sent_at datetime DEFAULT NULL,
            offer_expires_at datetime DEFAULT NULL,
            created_at datetime NOT NULL,
            updated_at datetime NOT NULL,
            PRIMARY KEY  (id),
            UNIQUE KEY uuid (uuid),
            KEY animation_status (animation_id,status),
            KEY animation_slot_status (animation_id,slot_uuid,status),
            KEY environment_updated (environment,updated_at),
            KEY group_uuid (group_uuid),
            KEY identity_key (animation_id,identity_key)
        ) ENGINE=InnoDB $collation;";
        $queries[] = "CREATE TABLE $directory (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            environment varchar(12) NOT NULL,
            public_id varchar(4) NOT NULL,
            active tinyint(1) NOT NULL,
            birth_year int(11) DEFAULT NULL,
            category varchar(40) NOT NULL,
            first_name varchar(80) NOT NULL DEFAULT '',
            last_name varchar(80) NOT NULL DEFAULT '',
            email varchar(254) NOT NULL DEFAULT '',
            phone varchar(40) NOT NULL DEFAULT '',
            email_hmac char(64) NOT NULL,
            phone_hmac char(64) NOT NULL,
            updated_at datetime NOT NULL,
            PRIMARY KEY  (id),
            UNIQUE KEY environment_public (environment,public_id),
            KEY environment_email (environment,email_hmac),
            KEY environment_phone (environment,phone_hmac)
        ) ENGINE=InnoDB $collation;";
        $queries[] = "CREATE TABLE $events (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            environment varchar(12) NOT NULL,
            event_type varchar(40) NOT NULL,
            reservation_uuid char(36) NOT NULL,
            created_at datetime NOT NULL,
            PRIMARY KEY  (id),
            KEY environment_id (environment,id)
        ) ENGINE=InnoDB $collation;";
        $queries[] = "CREATE TABLE $tokens (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            reservation_uuid char(36) NOT NULL,
            token_type varchar(20) NOT NULL,
            token_hash char(64) NOT NULL,
            expires_at datetime NOT NULL,
            used_at datetime DEFAULT NULL,
            created_at datetime NOT NULL,
            PRIMARY KEY  (id),
            UNIQUE KEY token_hash (token_hash),
            KEY reservation_type (reservation_uuid,token_type)
        ) ENGINE=InnoDB $collation;";
        $queries[] = "CREATE TABLE $nonces (
            nonce_hash char(64) NOT NULL,
            expires_at datetime NOT NULL,
            PRIMARY KEY  (nonce_hash),
            KEY expires_at (expires_at)
        ) ENGINE=InnoDB $collation;";
        foreach ($queries as $query) { dbDelta($query); }
        if (self::tables_are_innodb()) {
            update_option('openfablab_res_schema_version', OPENFABLAB_RES_SCHEMA_VERSION, false);
        }
    }

    public static function tables_are_innodb() {
        global $wpdb;
        foreach (['animations', 'reservations', 'directory', 'events', 'tokens', 'nonces'] as $name) {
            $table = self::table($name);
            $status = $wpdb->get_row($wpdb->prepare('SHOW TABLE STATUS LIKE %s', $table));
            if (!$status || strcasecmp((string) $status->Engine, 'InnoDB') !== 0) {
                return false;
            }
        }
        return true;
    }

    public static function event($environment, $type, $uuid) {
        global $wpdb;
        $wpdb->insert(self::table('events'), [
            'environment' => $environment,
            'event_type' => $type,
            'reservation_uuid' => $uuid,
            'created_at' => current_time('mysql', true),
        ], ['%s', '%s', '%s', '%s']);
    }
}
