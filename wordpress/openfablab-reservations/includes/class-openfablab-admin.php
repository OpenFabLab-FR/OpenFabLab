<?php
if (!defined('ABSPATH')) { exit; }

final class OpenFabLab_Admin {
    public static function menu() {
        add_options_page('OpenFabLab Reservations','OpenFabLab Reservations','manage_options',
            'openfablab-reservations',[__CLASS__,'render']);
    }
    public static function assets($hook) {
        if ($hook!=='settings_page_openfablab-reservations') { return; }
        foreach (['css'=>'style','js'=>'script'] as $ext=>$type) {
            $file='assets/admin.'.$ext;
            $version=substr(hash_file('sha256',OPENFABLAB_RES_PATH.$file),0,12);
            if ($type==='style') { wp_enqueue_style('openfablab-res-admin',plugins_url($file,OPENFABLAB_RES_FILE),[],$version); }
            else { wp_enqueue_script('openfablab-res-admin',plugins_url($file,OPENFABLAB_RES_FILE),[],$version,true); }
        }
    }
    public static function status($state,$secret,$secure,$storage) {
        if (!$storage) { return ['error','Erreur']; }
        if (!$secret || !$secure) { return ['action','Action requise']; }
        if (!$state['catalogue_at']) { return ['waiting','En attente du premier échange']; }
        if ($state['catalogue_at']<time()-900 || !$state['polled_at'] || $state['polled_at']<time()-120) {
            return ['action','Action requise'];
        }
        return ['connected','Connecté'];
    }
    private static function stamp($stamp) {
        return $stamp ? '<time datetime="'.esc_attr(gmdate('c',$stamp)).'" title="'.esc_attr(wp_date('d/m/Y H:i:s',$stamp)).'">'
            .esc_html('il y a '.human_time_diff($stamp,time())).'</time>' : '<span>Pas encore reçu</span>';
    }
    private static function environment($env,$secret,$secure,$storage) {
        try { $state=OpenFabLab_Relay::state($env); }
        catch (Throwable $error) {
            $storage=false;
            $state=['catalogue_at'=>0,'polled_at'=>0,'results_at'=>0,'animations'=>0,
                'queue'=>['pending'=>0,'processing'=>0,'retrying'=>0,'failed'=>0]];
        }
        [$kind,$label]=self::status($state,$secret,$secure,$storage);
        echo '<div class="ofl-connection"><div class="ofl-card-heading"><h3>'.($env==='production'?'Normal':'Test')
            .'</h3><span class="ofl-badge ofl-'.$kind.'">'.esc_html($label).'</span></div>';
        echo '<dl class="ofl-timings">';
        foreach (['catalogue_at'=>'Catalogue','polled_at'=>'Relève des demandes','results_at'=>'Dernier résultat'] as $key=>$text) {
            echo '<div><dt>'.esc_html($text).'</dt><dd>'.self::stamp($state[$key]).'</dd></div>';
        }
        echo '</dl><dl class="ofl-counts">';
        foreach (['animations'=>'Animations publiées','pending'=>'En attente','processing'=>'En traitement','retrying'=>'Reprises à vérifier'] as $key=>$text) {
            $number=$key==='animations'?$state[$key]:$state['queue'][$key];
            echo '<div><dd>'.esc_html((string)$number).'</dd><dt>'.esc_html($text).'</dt></div>';
        }
        echo '</dl>';
        if ($kind==='waiting') { echo '<p class="ofl-help">Le catalogue apparaîtra après le premier échange d’OpenFabLab. Aucune ouverture du NAS n’est nécessaire.</p>'; }
        elseif ($kind==='action') {
            echo '<p class="ofl-help">'.(!$secret?'Configurez la clé partagée avant le premier échange.'
                :(!$secure?'Cette page doit être consultée en HTTPS.':'Vérifiez que la synchronisation est active dans OpenFabLab.')).'</p>';
        } elseif ($kind==='error') { echo '<p class="ofl-help">Le stockage du relais doit être vérifié. Consultez le diagnostic avancé.</p>'; }
        echo '</div>';
    }
    private static function shortcode($env) {
        $id='ofl-shortcode-'.$env;
        echo '<label for="'.$id.'">'.($env==='production'?'Page publique':'Page de test').'</label><div class="ofl-copy"><input readonly id="'.$id.'" value="'
            .esc_attr('[openfablab_reservations environment="'.$env.'"]').'"><button type="button" class="button" data-openfablab-copy="'.$id.'">Copier</button></div>';
    }
    public static function render() {
        if (!current_user_can('manage_options')) { return; }
        if ($_SERVER['REQUEST_METHOD']==='POST' && isset($_POST['ofl_settings'])) {
            check_admin_referer('openfablab_connection_settings');
            $url=esc_url_raw(wp_unslash($_POST['privacy_url'] ?? ''));
            if ($url==='' || str_starts_with($url,'https://')) {
                update_option('openfablab_res_privacy_url',$url,false);
                update_option('openfablab_res_remove_on_uninstall',isset($_POST['remove_on_uninstall'])?'1':'0',false);
                echo '<div class="notice notice-success"><p>Réglages enregistrés.</p></div>';
            } else { echo '<div class="notice notice-error"><p>Utilisez une adresse HTTPS pour la confidentialité.</p></div>'; }
        }
        $secret=(bool)get_option('openfablab_res_sync_secret','');$secure=is_ssl();$storage=true;
        try { OpenFabLab_Database::assert_transactional(); } catch (Throwable $error) { $storage=false; }
        echo '<div class="wrap ofl-admin"><header class="ofl-admin-header"><img src="'.esc_url(plugins_url('assets/OpenFabLab-logo-horizontal.svg',OPENFABLAB_RES_FILE))
            .'" alt="OpenFabLab"><div><h1>OpenFabLab Reservations</h1><p>Version '.esc_html(OPENFABLAB_RES_VERSION).' · Catalogue public et réservations</p></div></header>';
        echo '<section class="ofl-card"><h2>Connexion à OpenFabLab</h2><p class="ofl-help">OpenFabLab décide des places et des inscriptions. WordPress reçoit le catalogue et transmet les demandes.</p>';
        self::environment('production',$secret,$secure,$storage);
        echo '<details class="ofl-details"><summary>Environnement Test</summary>';
        self::environment('test',$secret,$secure,$storage);
        echo '</details></section><section class="ofl-card"><h2>Page de réservation</h2><p class="ofl-help">Ajoutez ce shortcode à votre page WordPress.</p>';
        self::shortcode('production');
        echo '<details class="ofl-details"><summary>Shortcode de test</summary>';
        self::shortcode('test');
        echo '</details><p id="openfablab-copy-status" class="ofl-help" role="status" aria-live="polite"></p>';
        echo '<form method="post">';
        wp_nonce_field('openfablab_connection_settings');
        echo '<input type="hidden" name="ofl_settings" value="1"><label for="ofl-privacy">Page de confidentialité (facultatif)</label><input type="url" id="ofl-privacy" name="privacy_url" value="'
            .esc_attr(get_option('openfablab_res_privacy_url','')).'" placeholder="https://…"><p><button class="button button-primary">Enregistrer</button></p>';
        echo '<details class="ofl-details"><summary>Désinstallation</summary><label class="ofl-checkbox"><input type="checkbox" name="remove_on_uninstall" value="1" '
            .checked(get_option('openfablab_res_remove_on_uninstall','0'),'1',false).'> Effacer les données du plugin uniquement lors de sa désinstallation.</label><p class="ofl-help">La base OpenFabLab n’est jamais concernée.</p></details></form></section>';
        echo '<section class="ofl-card"><h2>Sécurité de la connexion</h2><p>Secret partagé : <span class="ofl-badge '.($secret?'ofl-connected':'ofl-action').'">'
            .($secret?'Configuré ✓':'À configurer').'</span></p><details class="ofl-details"><summary>'.($secret?'Régénérer le secret':'Configurer le secret').'</summary>';
        echo '<p class="ofl-help">La régénération coupe temporairement la liaison avec OpenFabLab. La nouvelle clé doit être enregistrée dans OpenFabLab avant la reprise des échanges. Elle n’est jamais affichée sur cette page.</p>';
        echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'">';
        wp_nonce_field('openfablab_connection_secret');
        echo '<input type="hidden" name="action" value="openfablab_connection_secret"><label class="ofl-checkbox"><input required type="checkbox" name="confirm" value="1"> Je confirme et conserverai la nouvelle clé dans un fichier privé.</label><p><button class="button" '
            .(!$secure?'disabled':'').'>'.($secret?'Régénérer':'Générer').' et télécharger la clé</button></p></form></details></section>';
        echo '<details class="ofl-card ofl-details"><summary>Diagnostic avancé</summary><dl class="ofl-diagnostic"><div><dt>Connexion HTTPS</dt><dd>'.($secure?'Disponible':'À vérifier')
            .'</dd></div><div><dt>Stockage InnoDB</dt><dd>'.($storage?'Disponible':'À vérifier').'</dd></div><div><dt>Protocole du relais</dt><dd>4 · révision 3</dd></div><div><dt>Échanges interactifs</dt><dd>15 secondes par défaut (réglage OpenFabLab)</dd></div><div><dt>Catalogue</dt><dd>90 secondes par défaut (réglage OpenFabLab)</dd></div></dl>';
        $old=get_option('openfablab_res_retired_storage','absent');
        if (in_array($old,['retained','retained_review'],true)) {
            echo '<p class="ofl-help">D’anciennes tables ont été conservées par précaution. Elles ne sont ni lues ni utilisées pour les nouvelles inscriptions.</p>';
        }
        echo '<p class="ofl-help">Le relais conserve les demandes jusqu’au retour du moteur. Un échange signé ne confirme pas une réservation. Les liens d’e-mail demandent une confirmation explicite.</p><p class="ofl-help">Aucune adresse publique OpenFabLab, aucun port entrant et aucun envoi d’e-mail par WordPress ne sont nécessaires.</p></details></div>';
    }
    public static function regenerate() {
        if (!current_user_can('manage_options') || !is_ssl() || $_SERVER['REQUEST_METHOD']!=='POST') {
            wp_die('Action refusée.','',['response'=>403]);
        }
        check_admin_referer('openfablab_connection_secret');
        if (($_POST['confirm'] ?? '')!=='1') { wp_die('Confirmez la régénération.','',['response'=>400]); }
        global $wpdb;
        OpenFabLab_Database::assert_transactional();
        $table=OpenFabLab_Database::table('relay_actions');
        // Do not rotate the encryption key while a live request or receipt exists.
        $locked=false;
        try {
            OpenFabLab_Database::connection_lock(); $locked=true;
            if ($wpdb->query('START TRANSACTION')===false) { throw new RuntimeException(); }
            $rows=$wpdb->get_results('SELECT action_id FROM '.$table.' WHERE expires_at>'.(int)time().' FOR UPDATE');
            if ($wpdb->last_error || $rows) { throw new RuntimeException(); }
            $secret=bin2hex(random_bytes(32));
            if (!update_option('openfablab_res_sync_secret',$secret,false)) { throw new RuntimeException(); }
            if ($wpdb->query('COMMIT')===false) { throw new RuntimeException(); }
        } catch (Throwable $error) {
            $wpdb->query('ROLLBACK');
            if ($locked) { OpenFabLab_Database::connection_unlock(); $locked=false; }
            wp_die('La clé n’a pas été changée. Attendez la fin des demandes et réessayez.','',['response'=>409]);
        } finally { if ($locked) { OpenFabLab_Database::connection_unlock(); } }
        nocache_headers();
        header('Referrer-Policy: no-referrer');
        header('X-Content-Type-Options: nosniff');
        header('Content-Type: text/plain; charset=utf-8');
        header('Content-Disposition: attachment; filename="openfablab-connexion-privee.txt"');
        echo $secret."\n";
        exit;
    }
}
