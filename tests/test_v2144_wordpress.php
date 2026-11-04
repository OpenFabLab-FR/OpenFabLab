<?php
// Actual PHP, in-memory WP options/hooks/shortcode blocks. No external service.
require __DIR__.'/test_v2141_wordpress.php';
class WP_Error {function __construct(public $code,public $message,public $data=[]) {}}
class WP_REST_Response {public $headers=[];function __construct(public $data){}function header($key,$value){$this->headers[$key]=$value;}}
$initial=$checks;
foreach(['2026-11-03'=>'2026-10-03','2026-03-31'=>'2026-02-28','2028-03-31'=>'2028-02-29','2026-01-31'=>'2025-12-31'] as $day=>$expected){check(OpenFabLab_Public::month_before(new DateTimeImmutable($day,new DateTimeZone('Europe/Paris')))->format('Y-m-d')===$expected,'clamped month '.$day);}
$zone=new DateTimeZone('Europe/Paris');$today=new DateTimeImmutable('today',$zone);$first=OpenFabLab_Public::month_before($today);$past=$today->modify('-10 days')->setTime(10,0);
$base=['id'=>'animation-fictional','kind'=>'animation','title'=>'Animation publique fictive','service_id'=>1,'start'=>$past->format('c'),'end'=>$past->modify('+2 hours')->format('c'),'signup_open_at'=>'','hide_before_opening'=>false,'public_until'=>$past->modify('+26 hours')->format('c'),'close_at'=>$past->format('c'),'information_url'=>'','availability_state'=>'ended','history_eligible'=>true];
$base['public_until']=$past->setTimestamp($past->modify('+2 hours')->getTimestamp()+86400)->format('c');
$snapshot=['version'=>1,'timezone'=>'Europe/Paris','coverage_start'=>$first->modify('monday this week')->format('Y-m-d'),'coverage_end'=>$today->modify('+80 days')->format('Y-m-d'),'history_start'=>$first->format('Y-m-d'),'calendar'=>[$base],'machines'=>[]];
check(OpenFabLab_Public::valid_snapshot($snapshot),'history allowlist valid');$options['openfablab_calendar_animations']='1';$options['openfablab_calendar_openlab']='1';
$original=$options;
foreach([true,false] as $eligible){$value=$snapshot;$value['calendar'][0]['history_eligible']=$eligible;$options['openfablab_public_snapshot_production']=['data'=>$value,'received_at'=>time()];$before=$options;check(count(OpenFabLab_Public::read('calendar','production')->data['items'])===($eligible?1:0),'history needs explicit source evidence '.$eligible);check($options===$before,'read endpoint writes nothing');}
$value=$snapshot;$badDay=$first->modify('-1 day')->setTime(10,0);foreach(['start','end','close_at','public_until'] as $field)$value['calendar'][0][$field]=$badDay->modify($field==='end'?'+2 hours':($field==='public_until'?'+26 hours':'+0 hours'))->format('c');
$value['calendar'][0]['public_until']=$badDay->setTimestamp($badDay->modify('+2 hours')->getTimestamp()+86400)->format('c');
$options['openfablab_public_snapshot_production']=['data'=>$value,'received_at'=>time()];check(OpenFabLab_Public::read('calendar','production')->data['items']===[],'week overlapping lower limit cannot expose previous day');
$options['openfablab_public_snapshot_production']=['data'=>$snapshot,'received_at'=>time()];check(OpenFabLab_Public::read('calendar','test') instanceof WP_Error,'Normal data not disclosed in Test');
foreach(['history_start'=>'2026-02-30','notes'=>'PRIVATE'] as $field=>$value){$bad=$snapshot;$bad[$field]=$value;check(!OpenFabLab_Public::valid_snapshot($bad),'reject malformed/unknown root '.$field);}
foreach(['yes',1,null,[]] as $flag){$bad=$snapshot;$bad['calendar'][0]['history_eligible']=$flag;check(!OpenFabLab_Public::valid_snapshot($bad),'history flag must be boolean');}
$bad=$snapshot;unset($bad['history_start']);check(!OpenFabLab_Public::valid_snapshot($bad),'history event cannot appear without negotiated window');
foreach(['participants','is_present','user_id','notes','manage_token'] as $field){$bad=$snapshot;$bad['calendar'][0][$field]='PRIVATE';check(!OpenFabLab_Public::valid_snapshot($bad),'private field refused '.$field);}
$old=$snapshot;unset($old['history_start'],$old['calendar'][0]['history_eligible']);check(OpenFabLab_Public::valid_snapshot($old),'2.14.3 format accepted without new capability');
$options=$original;$pages=[];
foreach(['fr','en'] as $language)foreach([false,true] as $title)foreach([false,true] as $multilingual)foreach(['machines','calendar','all','machines-first'] as $layout){
 $options['openfablab_public_language']=$language;$options['openfablab_public_machines_title']=$title?'1':'0';$options['openfablab_multilingual_enabled']=$multilingual?'1':'0';$assets=[];
 $kinds=$layout==='machines'?['machines']:($layout==='calendar'?['calendar']:($layout==='all'?['calendar','machines','reservations']:['machines','calendar','reservations']));
 $blocks=implode('',array_map(fn($kind)=>'<!-- wp:shortcode -->[openfablab_'.$kind.' environment="production"]<!-- /wp:shortcode -->',$kinds));
 $rendered=preg_replace_callback('/\[(openfablab_\w+) environment="production"\]/',fn($m)=>$shortcodes[$m[1]](['environment'=>'production']),$blocks);
 check(!preg_match('/\[openfablab_\w+/',$rendered),'Gutenberg-model output '.$layout);
 $configs=array_values(array_filter($assets,fn($row)=>is_string($row[1]??null)&&str_starts_with($row[1],'window.OpenFabLabPublic=')));
 $config=json_decode(substr($configs[0][1],strlen('window.OpenFabLabPublic='),-1),true);$pages[]=compact('language','title','multilingual','layout','rendered','config');
}
if(isset($argv[1]))file_put_contents($argv[1],json_encode($pages,JSON_PRETTY_PRINT|JSON_UNESCAPED_UNICODE));
echo ($checks-$initial)." new 2.14.4 WordPress checks passed\n";
