<?php
if (!defined('ABSPATH')) { exit; }
// Standalone page: no theme/analytics/third-party scripts can see the fragment.
add_action('template_redirect',function () {
    if (!isset($_GET['openfablab_action'])) { return; }
    nocache_headers();
    header('Cache-Control: private, no-store, max-age=0');
    header('X-Robots-Tag: noindex, nofollow');
    header('Referrer-Policy: no-referrer');
    header("Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
    $api=rest_url('openfablab/v1/public/');
    ?><!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Ma réservation — OpenFabLab</title><link rel="stylesheet" href="<?php echo esc_url(plugins_url('../assets/reservations.css',__FILE__)); ?>"></head><body><main class="openfablab-reservations" data-openfablab-link data-api="<?php echo esc_attr($api); ?>"><h1>Ma réservation</h1><p role="status" aria-live="polite">Vérification en cours…</p><div class="openfablab-link-buttons"></div><noscript>Contactez l’équipe pour gérer cette réservation sans JavaScript.</noscript></main><script src="<?php echo esc_url(plugins_url('../assets/link.js',__FILE__)); ?>"></script></body></html><?php
    exit;
},0);
