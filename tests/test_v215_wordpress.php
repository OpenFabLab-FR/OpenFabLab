<?php
// Real plugin handlers; WordPress/Gutenberg host is represented by test doubles.
function current_user_can($capability){return $capability==='manage_options';}
function wp_nonce_field(...$arguments){}
function admin_url($path){return 'https://example.invalid/wp-admin/'.$path;}
function get_user_locale(){return $GLOBALS['fictional_admin_locale']??'fr_FR';}
function esc_url($text){return htmlspecialchars($text,ENT_QUOTES);}
function esc_html($text){return htmlspecialchars((string)$text,ENT_QUOTES);}
function checked($actual,$expected,$echo=true){$result=$actual===$expected?'checked="checked"':'';if($echo)echo $result;return $result;}
function selected($actual,$expected,$echo=true){$result=$actual===$expected?'selected="selected"':'';if($echo)echo $result;return $result;}
require __DIR__.'/test_v2144_wordpress.php';
$initial=$checks;
$native_labels=['fr'=>'Langue par défaut','en'=>'Default language','de'=>'Standardsprache','es'=>'Idioma predeterminado','fi'=>'Oletuskieli'];
foreach ($native_labels as $language=>$label) {
 $GLOBALS['fictional_admin_locale']=$language.'_XX';
 $options['openfablab_booking_page']='https://example.invalid/Enregistrer';
 ob_start();OpenFabLab_Public::settings();$html=ob_get_clean();
 check(str_contains($html,$label),'native administration label '.$language);
 check(str_contains($html,'https://example.invalid/Enregistrer'),'custom setting untouched '.$language);
 foreach (['Français','English','Deutsch','Español','Suomi'] as $name) {check(str_contains($html,$name),'native language name '.$name.' in '.$language);}
 check(OpenFabLab_I18n::literal('<p>[openfablab_calendar environment="production"]</p>')==='<p>[openfablab_calendar environment="production"]</p>','technical shortcode unchanged '.$language);
}
$GLOBALS['fictional_admin_locale']='fr_FR';
foreach (['fr','en','de','es','fi'] as $language) {
 $options['openfablab_public_language']=$language;
 $text=OpenFabLab_Public::text('Chargement…','Loading…');
 check(is_string($text)&&$text!=='','loading message '.$language);
 if (!in_array($language,['fr','en'],true)) {check($text!=='Chargement…','native loading translation '.$language);}
 ob_start();OpenFabLab_Public::settings();$html=ob_get_clean();
 foreach (['fr','en','de','es','fi'] as $code) {check(str_contains($html,'value="'.$code.'"'),'language setting '.$code.' in '.$language);}
 check(str_contains($html,'name="public_machines_title"'),'optional title retained');
}
foreach (['loaned','overdue','rental_available'] as $status) {
 $value=['version'=>1,'timezone'=>'Europe/Paris','coverage_start'=>'2026-11-01','coverage_end'=>'2026-12-01','calendar'=>[],
   'machines'=>[['id'=>'fictional','name'=>'Ressource fictive','status'=>$status,'reason'=>'','return_estimate'=>null]]];
 check(OpenFabLab_Public::valid_snapshot($value),'effective availability '.$status);
}
$pages=[];
foreach(['fr','en','de','es','fi'] as $language)foreach([false,true] as $title)foreach([false,true] as $multilingual)foreach(['machines','calendar','all','machines-first'] as $layout){
 $options['openfablab_public_language']=$language;$options['openfablab_public_machines_title']=$title?'1':'0';$options['openfablab_multilingual_enabled']=$multilingual?'1':'0';$assets=[];
 $kinds=$layout==='machines'?['machines']:($layout==='calendar'?['calendar']:($layout==='all'?['calendar','machines','reservations']:['machines','calendar','reservations']));
 $blocks=implode('',array_map(fn($kind)=>'<!-- wp:shortcode -->[openfablab_'.$kind.' environment="production"]<!-- /wp:shortcode -->',$kinds));
 $rendered=preg_replace_callback('/\[(openfablab_\w+) environment="production"\]/',fn($m)=>$shortcodes[$m[1]](['environment'=>'production']),$blocks);
 check(!preg_match('/\[openfablab_\w+/',$rendered),'shortcodes render '.$language.' '.$layout);
 $configs=array_values(array_filter($assets,fn($row)=>is_string($row[1]??null)&&str_starts_with($row[1],'window.OpenFabLabPublic=')));
 $config=json_decode(substr($configs[0][1],strlen('window.OpenFabLabPublic='),-1),true);$pages[]=compact('language','title','multilingual','layout','rendered','config');
}
if(isset($argv[1]))file_put_contents($argv[1],json_encode($pages,JSON_PRETTY_PRINT|JSON_UNESCAPED_UNICODE));
echo ($checks-$initial)." new 2.15.0 WordPress checks passed\n";
