<?php
if (!defined('ABSPATH')) { exit; }

/** Private, opt-in Test maintenance. Never calls mail, promotions or sync events. */
final class OpenFabLab_Test_Maintenance {
    private const COUNTED = ['confirmed', 'offer_pending', 'present', 'absent'];
    private const CANCELLABLE = ['confirmed', 'offer_pending', 'present', 'absent', 'waitlisted'];
    private const NONCE_ACTION = 'openfablab_res_test_maintenance';

    private static function guard($environment) {
        if (!is_user_logged_in() || !current_user_can('manage_options')) {
            throw new DomainException('Accès réservé aux administrateurs WordPress.');
        }
        if ($environment !== 'test') {
            throw new DomainException('Maintenance refusée : seul l’environnement Test est autorisé.');
        }
    }

    private static function positive_id($value) {
        if ((!is_string($value) && !is_int($value))
            || !preg_match('/^[1-9][0-9]*$/D', (string) $value)
            || filter_var($value, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]) === false) {
            throw new DomainException('Identifiant invalide.');
        }
        return (int) $value;
    }

    private static function check_database() {
        global $wpdb;
        if ($wpdb->last_error !== '') { throw new RuntimeException('database_read_failed'); }
    }

    private static function snapshot($environment, $service_id, $lock = false) {
        self::guard($environment);
        global $wpdb;
        $animations = OpenFabLab_Database::table('animations');
        $reservations = OpenFabLab_Database::table('reservations');
        $tokens = OpenFabLab_Database::table('tokens');
        $suffix = $lock ? ' FOR UPDATE' : '';
        $animation = $wpdb->get_row($wpdb->prepare(
            "SELECT id, service_id, environment, title, starts_at, ends_at, timezone, capacity, updated_at "
            . "FROM $animations WHERE environment = %s AND service_id = %d" . $suffix,
            'test', $service_id
        ), ARRAY_A);
        self::check_database();
        if (!$animation || $animation['environment'] !== 'test') {
            throw new DomainException('Animation Test introuvable.');
        }
        $mismatches = $wpdb->get_var($wpdb->prepare(
            "SELECT COUNT(*) FROM $reservations WHERE animation_id = %d AND environment <> %s",
            $animation['id'], 'test'
        ));
        self::check_database();
        if ($mismatches === null || (int) $mismatches !== 0) {
            throw new DomainException('Environnements incohérents : aucune maintenance possible.');
        }
        // Never read contact values, token hashes, directory or sync secret.
        $rows = $wpdb->get_results($wpdb->prepare(
            "SELECT id, uuid, animation_id, environment, first_name, last_name, public_id, status, "
            . "group_uuid, source, is_present, offer_expires_at, created_at, updated_at "
            . "FROM $reservations WHERE animation_id = %d AND environment = %s ORDER BY id LIMIT 1001" . $suffix,
            $animation['id'], 'test'
        ), ARRAY_A);
        self::check_database();
        if (!is_array($rows) || count($rows) > 1000) {
            throw new DomainException('Analyse limitée à 1 000 inscriptions par animation.');
        }
        $links = $wpdb->get_results($wpdb->prepare(
            "SELECT t.id, t.reservation_uuid, t.token_type, t.used_at, t.expires_at "
            . "FROM $tokens t JOIN $reservations r ON r.uuid = t.reservation_uuid "
            . "WHERE r.animation_id = %d AND r.environment = %s ORDER BY t.id" . $suffix,
            $animation['id'], 'test'
        ), ARRAY_A);
        self::check_database();
        if (!is_array($links)) { throw new RuntimeException('database_read_failed'); }
        $occupied = 0;
        foreach ($rows as $row) {
            if ($row['environment'] !== 'test' || (int) $row['animation_id'] !== (int) $animation['id']) {
                throw new DomainException('Environnements incohérents : aucune maintenance possible.');
            }
            $occupied += in_array($row['status'], self::COUNTED, true) ? 1 : 0;
        }
        return ['animation' => $animation, 'rows' => $rows, 'links' => $links,
            'occupied' => $occupied, 'available' => max(0, (int) $animation['capacity'] - $occupied)];
    }

    public static function diagnose($environment, $service_id) {
        try { return self::snapshot($environment, self::positive_id($service_id)); }
        catch (DomainException $error) { return new WP_Error('test_maintenance_refused', $error->getMessage()); }
        catch (Throwable $error) { return new WP_Error('test_maintenance_failed', 'Lecture impossible. Aucun nettoyage effectué.'); }
    }

    private static function plan($snapshot, $ids) {
        if (!is_array($ids) || !$ids || count($ids) > 100) {
            throw new DomainException('Sélectionner entre 1 et 100 inscriptions, sans sélection automatique.');
        }
        $ids = array_map([self::class, 'positive_id'], $ids);
        if (count(array_unique($ids)) !== count($ids)) { throw new DomainException('Sélection dupliquée.'); }
        sort($ids, SORT_NUMERIC);
        $selected = array_values(array_filter($snapshot['rows'], fn($row) => in_array((int) $row['id'], $ids, true)));
        if (count($selected) !== count($ids)) { throw new DomainException('Une inscription sélectionnée ne relève pas de cette animation Test.'); }
        $places = 0; $uuids = [];
        foreach ($selected as $row) {
            if ($row['environment'] !== 'test' || !in_array($row['status'], self::CANCELLABLE, true)) {
                throw new DomainException('Une inscription sélectionnée n’est pas annulable en maintenance Test.');
            }
            $places += in_array($row['status'], self::COUNTED, true) ? 1 : 0;
            $uuids[] = $row['uuid'];
            if (!empty($row['group_uuid'])) {
                foreach ($snapshot['rows'] as $member) {
                    if ($member['group_uuid'] === $row['group_uuid']
                        && !in_array($member['status'], ['cancelled', 'expired'], true)
                        && !in_array((int) $member['id'], $ids, true)) {
                        throw new DomainException('Sélectionner tous les membres non annulés du groupe lié. Aucun membre n’est ajouté automatiquement.');
                    }
                }
            }
        }
        $links = array_values(array_filter($snapshot['links'], fn($link) =>
            in_array($link['reservation_uuid'], $uuids, true) && $link['used_at'] === null));
        return ['ids' => $ids, 'rows' => $selected, 'places' => $places, 'links' => $links];
    }

    private static function fingerprint($snapshot, $plan, $issued) {
        // Stateless preview: no transient/option write during analysis or preview.
        $payload = wp_json_encode([get_current_user_id(), 'test', $snapshot, $plan['ids'], $issued]);
        return hash_hmac('sha256', $payload, wp_salt('nonce'));
    }

    private static function storage_ready() {
        global $wpdb;
        // The private audit uses the existing options table, without schema upgrade.
        foreach ([OpenFabLab_Database::table('animations'), OpenFabLab_Database::table('reservations'),
                  OpenFabLab_Database::table('tokens'), $wpdb->options] as $table) {
            $row = $wpdb->get_row($wpdb->prepare('SHOW TABLE STATUS WHERE Name = %s', $table));
            self::check_database();
            if (!$row || strcasecmp((string) $row->Engine, 'InnoDB') !== 0) {
                throw new DomainException('Maintenance refusée : animations, inscriptions, liens et journal doivent être transactionnels (InnoDB).');
            }
        }
    }

    private static function apply($environment, $service_id, $input) {
        // Defence in depth even if this private mutation is invoked outside the UI.
        self::guard($environment);
        self::guard($input['environment'] ?? null);
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST'
            || !is_string($input['_wpnonce'] ?? null)
            || !wp_verify_nonce($input['_wpnonce'], self::NONCE_ACTION)) {
            throw new DomainException('Requête ou nonce invalide.');
        }
        if (($input['confirmation'] ?? null) !== 'PURGER TEST ' . $service_id
            || ($input['orphans_confirmed'] ?? null) !== '1') {
            throw new DomainException('Confirmation exacte et déclaration d’inscriptions orphelines obligatoires.');
        }
        $issued = self::positive_id($input['preview_issued_at'] ?? '');
        if ($issued > time() || time() - $issued > 600 || !is_string($input['preview_fingerprint'] ?? null)) {
            throw new DomainException('Prévisualisation expirée. Relancer l’analyse.');
        }
        self::storage_ready();
        global $wpdb;
        if ($wpdb->query('START TRANSACTION') === false) { throw new RuntimeException('transaction_failed'); }
        try {
            $before = self::snapshot($environment, $service_id, true);
            $plan = self::plan($before, $input['reservation_ids'] ?? []);
            if (!hash_equals(self::fingerprint($before, $plan, $issued), $input['preview_fingerprint'])) {
                throw new DomainException('Les données ou la sélection ont changé. Relancer l’analyse et la prévisualisation.');
            }
            $now = gmdate('Y-m-d H:i:s');
            foreach ($plan['rows'] as $row) {
                $changed = $wpdb->update(OpenFabLab_Database::table('reservations'),
                    ['status' => 'cancelled', 'is_present' => 0, 'offer_expires_at' => null, 'updated_at' => $now],
                    ['id' => (int) $row['id'], 'uuid' => $row['uuid'], 'animation_id' => (int) $before['animation']['id'],
                     'environment' => 'test', 'status' => $row['status']]);
                if ($changed !== 1) { throw new RuntimeException('reservation_update_failed'); }
            }
            foreach ($plan['links'] as $link) {
                $changed = $wpdb->update(OpenFabLab_Database::table('tokens'), ['used_at' => $now],
                    ['id' => (int) $link['id'], 'reservation_uuid' => $link['reservation_uuid'], 'used_at' => null]);
                if ($changed !== 1) { throw new RuntimeException('token_update_failed'); }
            }
            $after = self::snapshot($environment, $service_id, true);
            if ($after['occupied'] !== $before['occupied'] - $plan['places']) {
                throw new RuntimeException('capacity_postcheck_failed');
            }
            $audit = ['date_utc' => $now, 'wordpress_user_id' => get_current_user_id(), 'environment' => 'test',
                'service_id' => $service_id, 'reservations_affected' => count($plan['rows']),
                'places_released' => $plan['places'], 'action' => 'cancel_test_orphans_local'];
            // Not a sync event. Insert and cancellation commit atomically. No PII.
            $saved = $wpdb->insert($wpdb->options, [
                'option_name' => 'openfablab_res_test_audit_' . wp_generate_uuid4(),
                'option_value' => wp_json_encode($audit), 'autoload' => 'no'], ['%s', '%s', '%s']);
            if ($saved !== 1) { throw new RuntimeException('audit_failed'); }
            if ($wpdb->query('COMMIT') === false) { throw new RuntimeException('commit_failed'); }
            return ['mode' => 'done', 'snapshot' => $after, 'before' => $before, 'plan' => $plan];
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            throw $error;
        }
    }

    public static function handle_request($input) {
        try {
            self::guard($input['environment'] ?? null);
            if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST'
                || !is_string($input['_wpnonce'] ?? null)
                || !wp_verify_nonce($input['_wpnonce'], self::NONCE_ACTION)) {
                throw new DomainException('Requête ou nonce invalide.');
            }
            $service_id = self::positive_id($input['service_id'] ?? '');
            $action = $input['openfablab_test_tool'] ?? '';
            if ($action === 'clean') { return self::apply($input['environment'], $service_id, $input); }
            if (!in_array($action, ['analyse', 'preview'], true)) { throw new DomainException('Action inconnue.'); }
            $snapshot = self::snapshot('test', $service_id);
            $result = ['mode' => 'analyse', 'snapshot' => $snapshot];
            if ($action === 'preview') {
                $plan = self::plan($snapshot, $input['reservation_ids'] ?? []);
                $issued = time();
                $result += ['plan' => $plan, 'issued' => $issued, 'fingerprint' => self::fingerprint($snapshot, $plan, $issued)];
                $result['mode'] = 'preview';
            }
            return $result;
        } catch (DomainException $error) {
            return new WP_Error('test_maintenance_refused', $error->getMessage());
        } catch (Throwable $error) {
            return new WP_Error('test_maintenance_failed', 'Opération non validée. Vérifier le diagnostic avant de réessayer.');
        }
    }

    private static function fields($service_id) {
        wp_nonce_field(self::NONCE_ACTION);
        echo '<input type="hidden" name="environment" value="test"><input type="hidden" name="service_id" value="' . esc_attr((string) $service_id) . '">';
    }

    public static function render($result = null) {
        if (!is_user_logged_in() || !current_user_can('manage_options')) { return; }
        echo '<section id="openfablab-test-maintenance" style="margin-top:2rem;padding-top:1rem;border-top:2px solid #ccd0d4;max-width:100%">';
        echo '<h2>Outils de données Test</h2><p><strong>Cette opération concerne uniquement l’environnement Test.</strong> Normal est exclu côté serveur.</p>';
        echo '<p>Analyse privée, sans coordonnées de contact. Aucune inscription n’est déclarée orpheline automatiquement : comparer les UUID et dates avec le NAS. Ne sélectionner que les anciens essais dont l’absence du NAS a été vérifiée.</p>';
        echo '<form method="post">'; wp_nonce_field(self::NONCE_ACTION);
        echo '<input type="hidden" name="environment" value="test"><label for="openfablab-test-service">service_id OpenFabLab </label>';
        echo '<input id="openfablab-test-service" type="number" min="1" step="1" name="service_id" required> <button class="button" name="openfablab_test_tool" value="analyse">Analyser les données Test</button></form>';
        if (is_wp_error($result)) {
            echo '<div class="notice notice-error inline"><p>' . esc_html($result->get_error_message()) . '</p></div>';
        } elseif (is_array($result)) {
            self::render_analysis($result);
        }
        echo '<h3>Journal administrateur de maintenance Test</h3>';
        global $wpdb;
        $audit_rows = $wpdb->get_results($wpdb->prepare(
            "SELECT option_value FROM $wpdb->options WHERE option_name LIKE %s ORDER BY option_id DESC LIMIT 10",
            $wpdb->esc_like('openfablab_res_test_audit_') . '%'
        ), ARRAY_A);
        if (!$audit_rows) { echo '<p>Aucune opération de maintenance Test enregistrée.</p>'; }
        foreach ($audit_rows ?: [] as $row) {
            $audit = json_decode($row['option_value'], true);
            if (!is_array($audit) || ($audit['environment'] ?? '') !== 'test') { continue; }
            echo '<p>' . esc_html((string) ($audit['date_utc'] ?? '')) . ' UTC · utilisateur WordPress #'
                . esc_html((string) ($audit['wordpress_user_id'] ?? '')) . ' · Test · service_id '
                . esc_html((string) ($audit['service_id'] ?? '')) . ' · inscriptions : '
                . esc_html((string) ($audit['reservations_affected'] ?? '')) . ' · places libérées : '
                . esc_html((string) ($audit['places_released'] ?? '')) . ' · annulation locale de maintenance</p>';
        }
        echo '</section>';
    }

    private static function render_analysis($result) {
        $snapshot = $result['snapshot']; $animation = $snapshot['animation'];
        echo '<h3>' . esc_html($animation['title']) . '</h3><p>Test · service_id '
            . esc_html((string) $animation['service_id']) . ' · ID interne WordPress '
            . esc_html((string) $animation['id']) . ' · ' . esc_html($animation['starts_at']) . ' → '
            . esc_html($animation['ends_at']) . ' UTC · fuseau ' . esc_html($animation['timezone']) . '</p>';
        echo '<p>Capacité ' . esc_html((string) $animation['capacity']) . ' − '
            . esc_html((string) $snapshot['occupied']) . ' places occupées = '
            . esc_html((string) $snapshot['available']) . ' disponibles (minimum zéro).</p>';
        echo '<p>Chaque ligne confirmée, place proposée, présente ou absente consomme une place. Annulée, expirée ou en liste d’attente : zéro. Un accompagnateur est une autre ligne du même groupe. « En ligne » est un canal, pas une preuve d’origine local/NAS.</p>';
        if ($result['mode'] === 'done') {
            echo '<div class="notice notice-success inline"><p>Maintenance Test terminée ; inscriptions conservées et liens inutilisables. Avant : '
                . esc_html((string) $result['before']['occupied']) . ' occupées / '
                . esc_html((string) $result['before']['available']) . ' disponibles. Après : '
                . esc_html((string) $snapshot['occupied']) . ' occupées / '
                . esc_html((string) $snapshot['available']) . ' disponibles.</p></div>';
        }
        echo '<form method="post">'; self::fields($animation['service_id']);
        echo '<div style="max-width:100%;overflow-x:auto"><table class="widefat striped"><thead><tr><th>Sélection</th><th>ID / UUID</th><th>Participant</th><th>Dates UTC</th><th>Statut</th><th>Capacité</th><th>Groupe / personnes liées</th><th>Canal</th></tr></thead><tbody>';
        $labels = ['confirmed' => 'Confirmée', 'offer_pending' => 'Place proposée', 'present' => 'Présent',
            'absent' => 'Absent', 'waitlisted' => 'Liste d’attente', 'cancelled' => 'Annulée', 'expired' => 'Expirée'];
        foreach ($snapshot['rows'] as $row) {
            $counts = in_array($row['status'], self::COUNTED, true);
            echo '<tr><td>';
            if (in_array($row['status'], self::CANCELLABLE, true)) {
                echo '<label><input type="checkbox" name="reservation_ids[]" value="' . esc_attr((string) $row['id']) . '"> #'
                    . esc_html((string) $row['id']) . '</label>';
            } else { echo '—'; }
            echo '</td><td>#' . esc_html((string) $row['id']) . '<br><code style="overflow-wrap:anywhere">'
                . esc_html($row['uuid']) . '</code></td><td>' . esc_html($row['first_name'] . ' ' . $row['last_name']);
            if ($row['public_id']) { echo '<br>Usager #' . esc_html($row['public_id']); }
            echo '</td><td>Création : ' . esc_html($row['created_at']) . '<br>Modification : ' . esc_html($row['updated_at'])
                . '</td><td>' . esc_html($labels[$row['status']] ?? $row['status']) . '<br>Annulation : '
                . ($row['status'] === 'cancelled' ? 'Oui' : 'Non') . '<br>Liste d’attente : '
                . ($row['status'] === 'waitlisted' ? 'Oui' : 'Non') . '</td><td>Compte actuellement : '
                . ($counts ? 'Oui' : 'Non') . '<br>Places consommées : ' . ($counts ? '1' : '0') . '</td><td>';
            if ($row['group_uuid']) {
                echo '<code style="overflow-wrap:anywhere">' . esc_html($row['group_uuid']) . '</code><br>';
                foreach ($snapshot['rows'] as $member) {
                    if ($member['group_uuid'] === $row['group_uuid']) {
                        echo '#' . esc_html((string) $member['id']) . ' ' . esc_html($member['first_name'] . ' ' . $member['last_name']) . '<br>';
                    }
                }
            } else { echo 'Sans groupe'; }
            echo '</td><td>' . esc_html($row['source']) . '</td></tr>';
        }
        echo '</tbody></table></div><p><button class="button" name="openfablab_test_tool" value="preview">Prévisualiser le nettoyage</button></p></form>';
        if ($result['mode'] === 'preview') {
            $plan = $result['plan'];
            echo '<h4>Prévisualisation — aucune écriture</h4><p>' . esc_html((string) count($plan['rows']))
                . ' inscriptions sélectionnées · ' . esc_html((string) $plan['places']) . ' places libérables · '
                . esc_html((string) count($plan['links'])) . ' liens inutilisables après validation (annulation et offres).</p><ul>';
            foreach ($plan['rows'] as $row) {
                echo '<li>#' . esc_html((string) $row['id']) . ' · ' . esc_html($row['uuid']) . ' · '
                    . esc_html($row['status']) . ' → cancelled ; historique conservé.</li>';
            }
            echo '</ul><p>Aucun nouvel événement NAS, e-mail ou promotion de liste d’attente. Les événements historiques existants restent conservés ; une reprise ancienne du curseur de synchronisation peut encore les lire. Ne pas utiliser cet outil pour annuler une inscription connue du NAS.</p>';
            echo '<form method="post">'; self::fields($animation['service_id']);
            foreach ($plan['ids'] as $id) { echo '<input type="hidden" name="reservation_ids[]" value="' . esc_attr((string) $id) . '">'; }
            echo '<input type="hidden" name="preview_issued_at" value="' . esc_attr((string) $result['issued']) . '">';
            echo '<input type="hidden" name="preview_fingerprint" value="' . esc_attr($result['fingerprint']) . '">';
            echo '<p><label><input type="checkbox" name="orphans_confirmed" value="1" required> Je confirme que toutes les inscriptions sélectionnées sont des essais Test orphelins, absents du NAS actuel, et que les groupes liés sont complets.</label></p>';
            echo '<p><label>Pour confirmer, saisir exactement <strong>PURGER TEST ' . esc_html((string) $animation['service_id'])
                . '</strong><br><input type="text" name="confirmation" autocomplete="off" required></label></p>';
            echo '<p><button class="button button-secondary" name="openfablab_test_tool" value="clean">Annuler les inscriptions Test orphelines sélectionnées</button></p></form>';
        }
    }
}
