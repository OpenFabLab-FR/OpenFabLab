<?php
/**
 * Plugin Name: OpenFabLab Reservations
 * Description: Catalogue public et relais sécurisé sortant du moteur OpenFabLab.
 * Version: 2.8.1
 * Requires PHP: 8.1
 * License: MIT
 * Text Domain: openfablab-reservations
 */
if (!defined('ABSPATH')) { exit; }
define('OPENFABLAB_RES_VERSION','2.8.1');
define('OPENFABLAB_RES_SCHEMA_VERSION','2.8.1-relay2');
define('OPENFABLAB_RES_FILE',__FILE__);
define('OPENFABLAB_RES_PATH',plugin_dir_path(__FILE__));
foreach (['database','relay','api','admin'] as $name) {
    require_once OPENFABLAB_RES_PATH.'includes/class-openfablab-'.$name.'.php';
}
require_once OPENFABLAB_RES_PATH.'includes/public-link.php';
add_filter('rest_pre_serve_request',['OpenFabLab_Relay','serve'],20,4);
add_filter('cron_schedules',function($schedules) {
    $schedules['openfablab_five_minutes']=['interval'=>300,'display'=>'Toutes les 5 minutes'];
    return $schedules;
});
function openfablab_res_install() {
    OpenFabLab_Database::install();
    if (!wp_next_scheduled('openfablab_relay_maintenance')) {
        wp_schedule_event(time()+60,'openfablab_five_minutes','openfablab_relay_maintenance');
    }
}
register_activation_hook(__FILE__,'openfablab_res_install');
register_deactivation_hook(__FILE__,function() {
    wp_clear_scheduled_hook('openfablab_res_maintenance');
    wp_clear_scheduled_hook('openfablab_relay_maintenance');
    // Durable requests and connection settings survive deactivation.
});
add_action('plugins_loaded',function() {
    if (get_option('openfablab_res_schema_version')!==OPENFABLAB_RES_SCHEMA_VERSION) { openfablab_res_install(); }
});
add_action('rest_api_init',['OpenFabLab_API','register']);
add_action('openfablab_relay_maintenance',['OpenFabLab_Relay','maintenance']);
add_action('admin_menu',['OpenFabLab_Admin','menu']);
add_action('admin_enqueue_scripts',['OpenFabLab_Admin','assets']);
add_action('admin_post_openfablab_connection_secret',['OpenFabLab_Admin','regenerate']);

function openfablab_res_shortcode($attributes) {
    $attributes = shortcode_atts(['environment' => 'test'], $attributes, 'openfablab_reservations');
    $environment = in_array($attributes['environment'], ['test', 'production'], true)
        ? $attributes['environment'] : 'test';
    $style_version = substr(hash_file('sha256', OPENFABLAB_RES_PATH . 'assets/reservations.css'), 0, 12);
    wp_enqueue_style('openfablab-reservations', plugins_url('assets/reservations.css', __FILE__), [], $style_version);
    wp_enqueue_script('openfablab-jsqr', plugins_url('assets/jsQR-1.4.0.js', __FILE__), [], '1.4.0', true);
    // Content hashes invalidate stale forms independently of the plugin version.
    $script_version = substr(hash_file('sha256', OPENFABLAB_RES_PATH . 'assets/family.js'), 0, 12);
    wp_enqueue_script('openfablab-reservations', plugins_url('assets/family.js', __FILE__), [], $script_version, true);
    wp_add_inline_script('openfablab-reservations', 'window.OpenFabLabReservations=' . wp_json_encode([
        'api' => esc_url_raw(rest_url('openfablab/v1/public/')),
        'privacy' => esc_url_raw(get_option('openfablab_res_privacy_url', '')),
        'family' => true,
    ]) . ';', 'before');
    $id = 'openfablab-res-' . wp_generate_password(8, false, false);
    ob_start();
    ?>
    <section id="<?php echo esc_attr($id); ?>" class="openfablab-reservations" data-environment="<?php echo esc_attr($environment); ?>" aria-label="Réservations des animations">
        <?php if ($environment === 'test') : ?><p class="openfablab-test-label">Environnement de test OpenFabLab</p><?php endif; ?>
        <div class="openfablab-status" role="status" aria-live="polite">Chargement des animations…</div>
        <div class="openfablab-animation-list"></div>
        <div class="openfablab-form-host"></div>
        <noscript>Pour réserver sans JavaScript, contactez l’équipe ou utilisez la borne OpenFabLab.</noscript>
    </section>
    <?php
    return ob_get_clean();
}
add_shortcode('openfablab_reservations', 'openfablab_res_shortcode');

add_filter('wp_robots', function ($robots) {
    global $post;
    if ($post instanceof WP_Post && strpos($post->post_content, '[openfablab_reservations') !== false
        && preg_match('/environment=["\']test["\']/', $post->post_content)) {
        $robots['noindex'] = true;
        $robots['nofollow'] = true;
    }
    return $robots;
});
