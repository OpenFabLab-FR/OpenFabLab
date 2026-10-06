<?php
if (!defined('WP_UNINSTALL_PLUGIN')) { exit; }
if (get_option('openfablab_res_remove_on_uninstall') !== '1') { return; }

global $wpdb;
foreach (['nonces', 'tokens', 'events', 'reservations', 'directory', 'animations', 'relay_catalogues', 'relay_actions'] as $name) {
    $table = $wpdb->prefix . 'openfablab_' . $name;
    $wpdb->query("DROP TABLE IF EXISTS `$table`");
}
foreach (['schema_version', 'sync_secret', 'last_sync', 'from_name', 'from_email',
          'reply_to', 'test_prefix', 'privacy_url', 'remove_on_uninstall', 'email_settings'] as $key) {
    delete_option('openfablab_res_' . $key);
}
foreach (['production','test'] as $environment) {
    foreach (['catalogue','poll','results'] as $key) { delete_option('openfablab_relay_'.$key.'_'.$environment); }
}
