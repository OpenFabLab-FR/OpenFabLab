<?php
if (!defined('ABSPATH')) { exit; }

/** OpenFabLab owns new bookings. WordPress is an optional signed gateway. */
final class OpenFabLab_Family_Gateway {
    public static function call($action, array $data) {
        // No inbound core URL, network request or capacity engine in WordPress.
        return $action==='catalogue'
            ? OpenFabLab_Relay::public_catalogue($data['environment'] ?? '')
            : OpenFabLab_Relay::enqueue($action,$data);
    }
}
