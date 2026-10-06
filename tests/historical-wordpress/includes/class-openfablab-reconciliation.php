<?php
if (!defined('ABSPATH')) { exit; }

/** Catalog only: reservations, events, tokens and customer emails are untouched. */
final class OpenFabLab_Reconciliation {
    public static function environment($body) {
        $environment = $body['environment'] ?? '';
        if (!in_array($environment, ['test', 'production'], true)) {
            throw new InvalidArgumentException('Environnement invalide.');
        }
        return $environment;
    }

    public static function snapshot(WP_REST_Request $request) {
        if (OpenFabLab_Bookings::historical_engine_disabled()) { return OpenFabLab_API::legacy_disabled($request); }
        global $wpdb;
        $body = json_decode($request->get_body(), true);
        try {
            if (!is_array($body)) { throw new InvalidArgumentException(); }
            $env = self::environment($body);
            $animations = $body['animations'] ?? null;
            if (!is_array($animations) || count($animations) > 10000) { throw new InvalidArgumentException(); }
            $ids = [];
            foreach ($animations as $animation) {
                $id = $animation['service_id'] ?? null;
                if (!is_array($animation) || !is_int($id) || $id <= 0 || isset($ids[$id])
                    || ($animation['environment'] ?? '') !== $env) { throw new InvalidArgumentException(); }
                $ids[$id] = true;
            }
        } catch (Throwable $error) {
            return new WP_Error('bad_snapshot', 'Catalogue canonique invalide.', ['status' => 400]);
        }
        $table = OpenFabLab_Database::table('animations');
        if ($wpdb->query('START TRANSACTION') === false) {
            return new WP_Error('snapshot_failed', 'Transaction indisponible.', ['status' => 500]);
        }
        try {
            // Same row locks as the public reservation path: fresh reservations
            // cannot be overwritten. Only configuration is ever written here.
            $known = $wpdb->get_results($wpdb->prepare("SELECT * FROM $table WHERE environment=%s ORDER BY id FOR UPDATE", $env), ARRAY_A);
            if (!is_array($known) || !empty($wpdb->last_error)) { throw new RuntimeException(); }
            foreach ($animations as $animation) {
                $item = new WP_REST_Request('POST');
                $item->set_body(wp_json_encode(['environment'=>$env, 'service_id'=>$animation['service_id'],
                    'command'=>'upsert', 'animation'=>$animation]));
                $result = OpenFabLab_API::sync_animations($item, true);
                if (is_wp_error($result) || empty($result['ok'])) { throw new RuntimeException(); }
            }
            $deactivated = 0;
            foreach ($known as $old) {
                if (isset($ids[(int)$old['service_id']])) { continue; }
                if ($wpdb->update($table, ['published'=>0, 'updated_at'=>gmdate('Y-m-d H:i:s')],
                    ['id'=>$old['id'], 'environment'=>$env]) === false) { throw new RuntimeException(); }
                ++$deactivated;
            }
            if ($wpdb->query('COMMIT') === false) { throw new RuntimeException(); }
            update_option('openfablab_res_catalog_' . $env, ['at'=>gmdate('c'), 'animations'=>count($ids),
                'deactivated'=>$deactivated, 'protocol'=>2], false);
            delete_option('openfablab_res_refresh_' . $env);
            return ['ok'=>true, 'animations'=>count($ids), 'deactivated'=>$deactivated];
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            update_option('openfablab_res_error_' . $env, 'Réconciliation refusée : vérifiez les paramètres et les inscriptions existantes.', false);
            return new WP_Error('snapshot_failed', 'Réconciliation refusée ; aucune réservation modifiée.', ['status'=>409]);
        }
    }

    public static function handle_admin_request($body) {
        if (!is_user_logged_in() || !current_user_can('manage_options') || ($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            wp_die('Accès refusé.');
        }
        check_admin_referer('openfablab_catalog_maintenance');
        $env = self::environment($body);
        $action = $body['catalog_action'] ?? '';
        if (!in_array($action, ['refresh','purge'], true)) { wp_die('Action inconnue.'); }
        if ($action === 'purge' && ($body['confirmation'] ?? '') !== 'RESYNCHRONISER ' . strtoupper($env)) {
            wp_die('Confirmation incorrecte. Aucune écriture.');
        }
        global $wpdb;
        if ($action === 'purge') {
            if (!get_option('openfablab_res_catalog_' . $env)) { wp_die('Validez d’abord une réconciliation OpenFabLab 2.7 pour cet environnement.'); }
            $table = OpenFabLab_Database::table('animations');
            if ($wpdb->query('START TRANSACTION') === false) { wp_die('Transaction indisponible.'); }
            $ok = $wpdb->query($wpdb->prepare("UPDATE $table SET published=0 WHERE environment=%s", $env));
            if ($ok === false || $wpdb->delete(OpenFabLab_Database::table('directory'), ['environment'=>$env]) === false) {
                $wpdb->query('ROLLBACK'); wp_die('Purge de configuration refusée.');
            }
            if ($wpdb->query('COMMIT') === false) { $wpdb->query('ROLLBACK'); wp_die('Validation refusée.'); }
        }
        update_option('openfablab_res_refresh_' . $env, gmdate('c'), false);
        $audit = get_option('openfablab_res_catalog_audit', []);
        $audit[] = ['at'=>gmdate('c'), 'actor'=>get_current_user_id(), 'environment'=>$env, 'action'=>$action];
        update_option('openfablab_res_catalog_audit', array_slice($audit, -100), false);
        return ['ok'=>true, 'environment'=>$env, 'action'=>$action];
    }

    public static function admin_action() {
        self::handle_admin_request(wp_unslash($_POST));
        wp_safe_redirect(admin_url('options-general.php?page=openfablab-reservations')); exit;
    }

    public static function render() {
        if (!current_user_can('manage_options')) { return; }
        echo '<hr><h2>Synchronisation et réconciliation</h2><p>OpenFabLab initie les échanges HTTPS. Une actualisation sera traitée lors du prochain passage du serveur, sans port entrant.</p>';
        global $wpdb;
        foreach (['test','production'] as $env) {
            $diag = get_option('openfablab_res_catalog_' . $env, []);
            $bookings = $wpdb->get_var($wpdb->prepare('SELECT COUNT(*) FROM ' . OpenFabLab_Database::table('reservations') . ' WHERE environment=%s', $env));
            echo '<h3>' . esc_html($env === 'test' ? 'Test' : 'Normal') . '</h3><p>Dernière tentative : ' . esc_html(get_option('openfablab_res_attempt_' . $env, 'aucune'))
                . ' · dernière réussite : ' . esc_html(get_option('openfablab_res_success_' . $env, 'aucune'))
                . ' · dernière erreur : ' . esc_html(get_option('openfablab_res_error_' . $env, '') ?: 'aucune')
                . ' · animations : ' . esc_html($diag['animations'] ?? 'inconnu') . ' · réservations : ' . esc_html($bookings ?? 'inconnu')
                . ' · protocole : 2 · plugin : ' . esc_html(OPENFABLAB_RES_VERSION) . '</p>';
            echo '<p>Actions NAS en attente : visibles sur OpenFabLab (non copiées dans WordPress). Demande d’actualisation : ' . (get_option('openfablab_res_refresh_' . $env) ? 'en attente' : 'aucune') . '</p>';
            echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
            wp_nonce_field('openfablab_catalog_maintenance');
            echo '<input type="hidden" name="action" value="openfablab_catalog_maintenance"><input type="hidden" name="environment" value="' . esc_attr($env) . '">';
            echo '<button class="button" name="catalog_action" value="refresh">Actualiser au prochain passage</button><p>OpenFabLab 2.7 requis pour la réconciliation. Purger uniquement la configuration reconstruisible : masque les animations et vide l’annuaire de cet environnement. Réservations, événements et liens d’annulation sont conservés. Le prochain snapshot republie le catalogue.</p>';
            echo '<label>Confirmer : RESYNCHRONISER ' . esc_html(strtoupper($env)) . ' <input name="confirmation" autocomplete="off"></label> <button class="button" name="catalog_action" value="purge">Purger la configuration et resynchroniser</button></form>';
        }
    }
}
