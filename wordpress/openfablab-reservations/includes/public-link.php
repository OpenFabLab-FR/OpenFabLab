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
    $language=get_option('openfablab_public_language','fr')==='en'?'en':'fr';
    $multilingual=get_option('openfablab_multilingual_enabled','0')==='1'?'1':'0';
    ?><!doctype html><html lang="<?php echo esc_attr($language); ?>"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title><?php echo $language==='en'?'Manage my booking':'Gérer ma réservation'; ?> — OpenFabLab</title><link rel="stylesheet" href="<?php echo esc_url(plugins_url('../assets/reservations.css',__FILE__)); ?>"><link rel="stylesheet" href="<?php echo esc_url(plugins_url('../assets/public.css',__FILE__)); ?>"></head><body><main class="openfablab-reservations" data-openfablab-link data-api="<?php echo esc_attr($api); ?>" data-language="<?php echo esc_attr($language); ?>" data-multilingual="<?php echo esc_attr($multilingual); ?>"><h1><?php echo $language==='en'?'Manage my booking':'Gérer ma réservation'; ?></h1><div class="openfablab-link-details"></div><p role="status" aria-live="polite"><?php echo $language==='en'?'Checking…':'Vérification en cours…'; ?></p><div class="openfablab-link-buttons"></div><noscript><?php echo $language==='en'?'Contact the team to manage this booking without JavaScript.':'Contactez l’équipe pour gérer cette réservation sans JavaScript.'; ?></noscript></main><script src="<?php echo esc_url(plugins_url('../assets/translations.js',__FILE__)); ?>"></script><script src="<?php echo esc_url(plugins_url('../assets/public.js',__FILE__)); ?>"></script><script src="<?php echo esc_url(plugins_url('../assets/link.js',__FILE__)); ?>"></script></body></html><?php
    exit;
},0);
