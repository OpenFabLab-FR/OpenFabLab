<?php
if (!defined('ABSPATH')) { exit; }

/** Native labels only. Never pass user content, URLs or secrets to this class. */
final class OpenFabLab_I18n {
    public static function text($native) {
        $locale=function_exists('get_user_locale')?get_user_locale():(function_exists('get_locale')?get_locale():'fr');
        $code=strtolower(substr((string)$locale,0,2));
        if (!in_array($code,['en','de','es','fi'],true)) { return $native; }
        static $catalogs=[];
        if (!isset($catalogs[$code])) {
            $catalogs[$code]=json_decode(file_get_contents(__DIR__.'/../languages/'.$code.'.json'),true) ?: [];
        }
        return $catalogs[$code][$native] ?? $native;
    }
    public static function literal($source_literal) {
        // Called only around constant HTML fragments in the PHP source, BEFORE
        // dynamic names/options are concatenated. No rendered-page translation.
        return preg_replace_callback('/(>)([^<>]+)(?=<|$)/u',function($match) {
            $key=trim($match[2]);
            if ($key==='') { return $match[0]; }
            $translated=self::text(html_entity_decode($key,ENT_QUOTES|ENT_HTML5,'UTF-8'));
            if ($translated===html_entity_decode($key,ENT_QUOTES|ENT_HTML5,'UTF-8')) { return $match[0]; }
            return $match[1].str_replace($key,htmlspecialchars($translated,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8'),$match[2]);
        },$source_literal);
    }
}
