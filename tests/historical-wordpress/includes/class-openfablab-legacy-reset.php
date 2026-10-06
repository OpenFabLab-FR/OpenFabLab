<?php
if (!defined('ABSPATH')) { exit; }

/** Explicit plugin-only cleanup; never calls OpenFabLab, mail or sync. */
final class OpenFabLab_Legacy_Reset {
    private const TABLES = ['tokens', 'events', 'directory', 'nonces', 'reservations', 'animations'];
    private static function guard() {
        if (!current_user_can('manage_options')) { wp_die('Accès refusé.'); }
        check_admin_referer('openfablab_legacy_reset');
    }
    private static function snapshot() {
        global $wpdb;
        $data = [];
        foreach (self::TABLES as $name) {
            $rows = $wpdb->get_results('SELECT * FROM ' . OpenFabLab_Database::table($name) . ' ORDER BY 1 LIMIT 10001', ARRAY_A);
            if (!is_array($rows) || $wpdb->last_error || count($rows) > 10000) {
                throw new RuntimeException('Sauvegarde impossible ou trop volumineuse. Aucun nettoyage effectué.');
            }
            $data[$name] = $rows;
        }
        return $data;
    }
    private static function digest($data) { return hash('sha256', wp_json_encode($data)); }
    private static function stable_digest($data) {
        // Anti-replay nonces can change during a harmless capabilities check.
        // They are backed up and deleted, but are not historical reservations.
        unset($data['nonces']);
        return self::digest($data);
    }
    public static function backup() {
        self::guard();
        try {
            $data = self::snapshot();
            $digest = self::digest($data);
            set_transient('openfablab_legacy_reset_' . get_current_user_id(), self::stable_digest($data), 900);
            nocache_headers();
            header('Content-Type: application/json; charset=utf-8');
            header('Content-Disposition: attachment; filename="openfablab-plugin-legacy-backup.json"');
            header('X-Content-Type-Options: nosniff');
            echo wp_json_encode(['format' => 'openfablab-plugin-legacy', 'version' => 1,
                'created_at' => gmdate('c'), 'sha256_tables' => $digest, 'tables' => $data]);
            exit;
        } catch (Throwable $error) { wp_die('Sauvegarde impossible. Aucun nettoyage effectué.'); }
    }
    public static function reset() {
        self::guard();
        if (($_POST['confirmation'] ?? '') !== 'NETTOYER LE PLUGIN'
            || empty($_POST['backup_saved']) || !OpenFabLab_Database::tables_are_innodb()) {
            wp_die('Confirmation et sauvegarde préalables requises.');
        }
        global $wpdb;
        $prior = get_transient('openfablab_legacy_reset_' . get_current_user_id());
        if (!$prior) { wp_die('Téléchargez d’abord une sauvegarde récente du plugin.'); }
        if ($wpdb->query('START TRANSACTION') === false) { wp_die('Transaction impossible. Aucun nettoyage effectué.'); }
        try {
            // Locks prevent a legacy admin action changing the backed-up state.
            foreach (self::TABLES as $name) {
                $wpdb->get_results('SELECT * FROM ' . OpenFabLab_Database::table($name) . ' FOR UPDATE', ARRAY_A);
                if ($wpdb->last_error) { throw new RuntimeException('lock_failed'); }
            }
            if (!hash_equals($prior, self::stable_digest(self::snapshot()))) {
                throw new RuntimeException('snapshot_changed');
            }
            foreach (self::TABLES as $name) {
                if ($wpdb->query('DELETE FROM ' . OpenFabLab_Database::table($name)) === false) {
                    throw new RuntimeException('delete_failed');
                }
            }
            if ($wpdb->query('COMMIT') === false) { throw new RuntimeException('commit_failed'); }
            delete_transient('openfablab_legacy_reset_' . get_current_user_id());
            wp_safe_redirect(admin_url('options-general.php?page=openfablab-reservations&legacy_reset=done'));
            exit;
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            wp_die('Nettoyage refusé. Retéléchargez une sauvegarde puis réessayez.');
        }
    }
    public static function render() {
        echo '<h2>Nettoyer l’ancien stockage WordPress</h2><p>Uniquement les références, réservations, annuaire et liens techniques de cet ancien plugin. Aucun compte, animation passée, statistique ou dossier de facturation OpenFabLab ne sera supprimé. Les réglages et le secret du plugin sont conservés.</p>';
        echo '<p>Ce passage ne doit se faire qu’en l’absence d’animations en cours ou à venir à récupérer. Le fichier de sauvegarde est privé et contient des données personnelles.</p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
        wp_nonce_field('openfablab_legacy_reset');
        echo '<input type="hidden" name="action" value="openfablab_legacy_backup"><button class="button">1. Télécharger la sauvegarde privée du plugin</button></form>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
        wp_nonce_field('openfablab_legacy_reset');
        echo '<input type="hidden" name="action" value="openfablab_legacy_reset"><p><label><input type="checkbox" name="backup_saved" value="1" required> J’ai conservé la sauvegarde téléchargée et n’ai aucune réservation active à récupérer.</label></p><p><label>Saisissez NETTOYER LE PLUGIN <input name="confirmation" required autocomplete="off"></label></p><button class="button">2. Nettoyer uniquement le plugin</button></form>';
    }
}
