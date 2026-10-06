<?php
/**
 * Plugin Name: OpenFabLab Reservations
 * Description: Réservations publiques via le moteur familial OpenFabLab.
 * Version: 2.8.1
 * Requires PHP: 8.1
 * License: MIT
 * Text Domain: openfablab-reservations
 */

if (!defined('ABSPATH')) {
    exit;
}

define('OPENFABLAB_RES_VERSION', '2.8.1');
// Schema revision also upgrades an already installed 2.5.0 corrective build.
define('OPENFABLAB_RES_SCHEMA_VERSION', '2.8.1');
define('OPENFABLAB_RES_FILE', __FILE__);
define('OPENFABLAB_RES_PATH', plugin_dir_path(__FILE__));

require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-database.php';
require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-relay.php';
require_once OPENFABLAB_RES_PATH . 'includes/public-link.php';
add_filter('rest_pre_serve_request',['OpenFabLab_Relay','serve'],20,4);
require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-slots.php';
require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-emails.php';
require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-bookings.php';
require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-api.php';
require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-family-gateway.php';
require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-legacy-reset.php';
add_action('admin_post_openfablab_legacy_backup', ['OpenFabLab_Legacy_Reset', 'backup']);
add_action('admin_post_openfablab_legacy_reset', ['OpenFabLab_Legacy_Reset', 'reset']);
require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-test-maintenance.php';
require_once OPENFABLAB_RES_PATH . 'includes/class-openfablab-reconciliation.php';
add_action('admin_post_openfablab_catalog_maintenance', ['OpenFabLab_Reconciliation', 'admin_action']);

register_activation_hook(__FILE__, function () {
    OpenFabLab_Database::install();
    if (!wp_next_scheduled('openfablab_res_maintenance')) {
        wp_schedule_event(time() + 60, 'openfablab_five_minutes', 'openfablab_res_maintenance');
    }
});

register_deactivation_hook(__FILE__, function () {
    wp_clear_scheduled_hook('openfablab_res_maintenance');
    // Reservations and settings intentionally survive deactivation.
});

add_filter('cron_schedules', function ($schedules) {
    $schedules['openfablab_five_minutes'] = ['interval' => 300, 'display' => 'Toutes les 5 minutes'];
    return $schedules;
});

add_action('plugins_loaded', function () {
    if (get_option('openfablab_res_schema_version') !== OPENFABLAB_RES_SCHEMA_VERSION) {
        OpenFabLab_Database::install();
    }
});

add_action('rest_api_init', ['OpenFabLab_API', 'register']);
add_action('openfablab_res_maintenance', ['OpenFabLab_Relay', 'maintenance']);

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

add_action('admin_menu', function () {
    add_options_page('OpenFabLab Reservations', 'OpenFabLab Reservations', 'manage_options',
        'openfablab-reservations', 'openfablab_res_admin_page');
});

function openfablab_res_admin_page() {
    if (!current_user_can('manage_options')) {
        wp_die(esc_html__('Accès refusé.', 'openfablab-reservations'));
    }
    if (function_exists('nocache_headers')) { nocache_headers(); }
    $new_secret = null;
    $test_result = null;
    $email_result = null;
    if (isset($_POST['openfablab_email_action'])) {
        $email_result = OpenFabLab_Emails::handle_request(wp_unslash($_POST));
    } elseif (isset($_POST['openfablab_test_tool'])) {
        $test_result = OpenFabLab_Test_Maintenance::handle_request(wp_unslash($_POST));
    } elseif ($_SERVER['REQUEST_METHOD'] === 'POST') {
        check_admin_referer('openfablab_res_settings');
        if (isset($_POST['openfablab_generate_secret'])) {
            $new_secret = bin2hex(random_bytes(32));
            update_option('openfablab_res_sync_secret', $new_secret, false);
        } else {
            update_option('openfablab_res_from_name', sanitize_text_field(wp_unslash($_POST['from_name'] ?? '')), false);
            update_option('openfablab_res_from_email', sanitize_email(wp_unslash($_POST['from_email'] ?? '')), false);
            update_option('openfablab_res_reply_to', sanitize_email(wp_unslash($_POST['reply_to'] ?? '')), false);
            update_option('openfablab_res_test_prefix', sanitize_text_field(wp_unslash($_POST['test_prefix'] ?? '')), false);
            update_option('openfablab_res_privacy_url', esc_url_raw(wp_unslash($_POST['privacy_url'] ?? '')), false);
            // Historical URL is preserved but never used by the outbound relay.
            update_option('openfablab_res_remove_on_uninstall', isset($_POST['remove_on_uninstall']) ? '1' : '0', false);
            echo '<div class="notice notice-success"><p>Réglages enregistrés.</p></div>';
        }
    }
    $tables_ok = OpenFabLab_Database::tables_are_innodb();
    global $wpdb;
    echo '<div class="wrap"><h1>OpenFabLab Reservations</h1>';
    echo '<p>Version ' . esc_html(OPENFABLAB_RES_VERSION) . ' · Tables transactionnelles : <strong>' . ($tables_ok ? 'InnoDB opérationnel' : 'À vérifier') . '</strong></p>';
    echo '<p>Schéma : ' . esc_html(get_option('openfablab_res_schema_version', 'non installé'))
        . ' · HTTPS : ' . (is_ssl() ? 'actif' : 'à vérifier')
        . ' · REST : ' . (rest_url('openfablab/v1/public/animations') ? 'disponible' : 'à vérifier')
        . ' · wp_mail : ' . (function_exists('wp_mail') ? 'disponible (délivrabilité à tester)' : 'indisponible') . '</p>';
    echo '<p>Dernier contact signé : ' . esc_html(get_option('openfablab_res_last_sync', 'Aucun')) . ' (ne garantit pas la réussite du catalogue).</p>';
    OpenFabLab_Relay::diagnostics();
    echo '<details><summary>Stockage historique et diagnostic</summary>';
    OpenFabLab_Reconciliation::render();
    if ($tables_ok) {
        foreach (['production' => 'Normal', 'test' => 'Test'] as $environment => $label) {
            $animations = (int) $wpdb->get_var($wpdb->prepare(
                'SELECT COUNT(*) FROM ' . OpenFabLab_Database::table('animations') . ' WHERE environment = %s',
                $environment
            ));
            $reservations = (int) $wpdb->get_var($wpdb->prepare(
                'SELECT COUNT(*) FROM ' . OpenFabLab_Database::table('reservations') . ' WHERE environment = %s',
                $environment
            ));
            echo '<p>' . esc_html($label) . ' : ' . esc_html((string) $animations)
                . ' animations · ' . esc_html((string) $reservations) . ' réservations</p>';
        }
    }
    if ($new_secret) {
        echo '<div class="notice notice-warning"><p>Copiez ce secret une seule fois dans Réglages → Structure et modules sur OpenFabLab. Il ne sera plus affiché :</p><code>' . esc_html($new_secret) . '</code></div>';
    }
    echo '</details>';
    echo '<p>Secret configuré : <strong>' . (get_option('openfablab_res_sync_secret') ? 'oui' : 'non') . '</strong>. Une régénération invalide la connexion NAS jusqu’à sa mise à jour.</p>';
    echo '<form method="post">'; wp_nonce_field('openfablab_res_settings');
    echo '<p><button class="button button-secondary" name="openfablab_generate_secret" value="1" type="submit">Générer / régénérer le secret</button></p></form>';
    echo '<form method="post">'; wp_nonce_field('openfablab_res_settings');
    $fields = [
        'from_name' => ['Nom expéditeur', 'openfablab_res_from_name', get_bloginfo('name')],
        'from_email' => ['E-mail expéditeur', 'openfablab_res_from_email', get_option('admin_email')],
        'reply_to' => ['Répondre à', 'openfablab_res_reply_to', get_option('admin_email')],
        'test_prefix' => ['Préfixe des e-mails de test', 'openfablab_res_test_prefix', '[TEST OpenFabLab]'],
        'privacy_url' => ['Lien de confidentialité', 'openfablab_res_privacy_url', ''],
    ];
    echo '<table class="form-table"><tbody>';
    foreach ($fields as $key => $field) {
        echo '<tr><th><label for="openfablab-' . esc_attr($key) . '">' . esc_html($field[0]) . '</label></th><td><input class="regular-text" id="openfablab-' . esc_attr($key) . '" name="' . esc_attr($key) . '" value="' . esc_attr(get_option($field[1], $field[2])) . '"></td></tr>';
    }
    echo '</tbody></table>';
    echo '<label><input type="checkbox" name="remove_on_uninstall" value="1" ' . checked(get_option('openfablab_res_remove_on_uninstall'), '1', false) . '> Supprimer les données seulement lors d’une désinstallation volontaire</label>';
    submit_button('Enregistrer'); echo '</form>';
    openfablab_res_admin_shortcodes();
    echo '<p><strong>Modèles historiques :</strong> non utilisés pour les nouvelles réservations. OpenFabLab confirme les groupes et propose les places automatiquement, par SMTP.</p>';
    OpenFabLab_Emails::render($email_result);
    OpenFabLab_Test_Maintenance::render($test_result);
    OpenFabLab_Legacy_Reset::render();
    echo '</div>';
}

function openfablab_res_admin_shortcodes() {
    echo '<h2>Shortcodes des pages de réservation</h2>';
    foreach (['production' => ['Réservations normales', 'À utiliser sur la page publique habituelle de réservation.'],
              'test' => ['Réservations de test', 'Environnement séparé destiné aux essais.']] as $environment => $texts) {
        $id = 'openfablab-shortcode-' . $environment;
        echo '<h3>' . esc_html($texts[0]) . '</h3><p>' . esc_html($texts[1]) . '</p>';
        echo '<p><input readonly class="large-text code" style="max-width:36rem" aria-label="' . esc_attr($texts[0])
            . '" id="' . esc_attr($id) . '" value="' . esc_attr('[openfablab_reservations environment="' . $environment . '"]')
            . '"> <button type="button" class="button" data-openfablab-copy="' . esc_attr($id) . '">Copier</button></p>';
    }
    echo '<p id="openfablab-copy-status" role="status" aria-live="polite"></p>';
    ?>
    <script>
    document.querySelectorAll('[data-openfablab-copy]').forEach(button => {
      button.addEventListener('click', async () => {
        const input = document.getElementById(button.dataset.openfablabCopy);
        const status = document.getElementById('openfablab-copy-status');
        try {
          if (!navigator.clipboard) throw new Error('clipboard unavailable');
          await navigator.clipboard.writeText(input.value);
          status.textContent = 'Shortcode copié.';
        } catch (_) {
          input.focus(); input.select();
          status.textContent = 'Shortcode sélectionné : utilisez la commande Copier de votre appareil.';
        }
      });
    });
    </script>
    <?php
}

add_action('admin_post_nopriv_openfablab_cancel', ['OpenFabLab_Bookings', 'cancellation_page']);
add_action('admin_post_openfablab_cancel', ['OpenFabLab_Bookings', 'cancellation_page']);
add_action('admin_post_nopriv_openfablab_offer', ['OpenFabLab_Bookings', 'offer_page']);
add_action('admin_post_openfablab_offer', ['OpenFabLab_Bookings', 'offer_page']);
