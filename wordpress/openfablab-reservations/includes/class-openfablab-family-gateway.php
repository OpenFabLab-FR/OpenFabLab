<?php
if (!defined('ABSPATH')) { exit; }

/** OpenFabLab owns new bookings. WordPress is an optional signed gateway. */
final class OpenFabLab_Family_Gateway {
    public static function call($action, array $data) {
        $base = rtrim((string) get_option('openfablab_res_core_url', ''), '/');
        $secret = (string) get_option('openfablab_res_sync_secret', '');
        if (!preg_match('#^https://[^/?\#]+(?:/[^?\#]*)?$#D', $base) || !$secret
            || !in_array($action, ['catalogue', 'identify', 'contact', 'reserve'], true)) {
            return new WP_Error('openfablab_connection', 'La connexion au moteur OpenFabLab doit être configurée par l’équipe.', ['status' => 503]);
        }
        if ($action === 'identify') {
            $data['client_bucket'] = hash_hmac('sha256', (string) ($_SERVER['REMOTE_ADDR'] ?? ''), wp_salt('auth'));
        }
        $body = wp_json_encode($data);
        $stamp = (string) time(); $nonce = bin2hex(random_bytes(24));
        $route = '/api/reservations/familles/' . $action;
        $canonical = $stamp . "\n" . $nonce . "\nPOST\n" . $route . "\n" . hash('sha256', $body);
        $response = wp_safe_remote_post($base . $route, [
            'timeout' => 15, 'redirection' => 0, 'sslverify' => true,
            'headers' => ['Content-Type' => 'application/json', 'X-OpenFabLab-Timestamp' => $stamp,
                'X-OpenFabLab-Nonce' => $nonce, 'X-OpenFabLab-Signature' => hash_hmac('sha256', $canonical, $secret)],
            'body' => $body,
        ]);
        if (is_wp_error($response)) {
            return new WP_Error('openfablab_unavailable', 'OpenFabLab est temporairement indisponible. Réessayez avec la même demande : aucune confirmation ne peut être donnée ici.', ['status' => 503]);
        }
        $status = wp_remote_retrieve_response_code($response);
        $value = json_decode(wp_remote_retrieve_body($response), true);
        if (!is_array($value) || $status < 200 || $status >= 300) {
            return new WP_Error('openfablab_refused', is_array($value) ? (string) ($value['message'] ?? 'Demande refusée.') : 'Réponse OpenFabLab invalide.', ['status' => $status === 409 ? 409 : 503]);
        }
        $result = new WP_REST_Response($value);
        $result->header('Cache-Control', 'private, no-store, max-age=0');
        $result->header('Referrer-Policy', 'no-referrer');
        return $result;
    }
}
