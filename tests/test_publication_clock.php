<?php
// Pure projection of signed catalogue snapshots. No WordPress/DB/network used.
define('ABSPATH',__DIR__);
require dirname(__DIR__).'/wordpress/openfablab-reservations/includes/class-openfablab-relay.php';
$checks=[];
function check($ok,$label){global $checks;if(!$ok)throw new Exception($label);$checks[]=$label;}
function example($end,$hidden=false) {
    return ['service_id'=>1,'title'=>'Atelier fictif','booking_mode'=>'whole','available'=>4,'waitlist_enabled'=>true,
        'availability_state'=>'not_open','waiting'=>0,'waiting_limit'=>4,'slots'=>[],
        'publication'=>['starts_at'=>gmdate('c',strtotime($end)-7200),'ends_at'=>$end,'public_until'=>gmdate('c',strtotime($end)+86400),
            'signup_open_at'=>gmdate('c',strtotime($end)-172800),'signup_open_label'=>'Ouverture fictive','close_minutes'=>0,'hide_before_opening'=>$hidden]];
}
foreach (['2026-03-28T22:00:00+00:00','2026-10-24T21:00:00+00:00'] as $end) {
    $item=example($end);$t=strtotime($end);$open=strtotime($item['publication']['signup_open_at']);
    check(OpenFabLab_Relay::visible_catalogue([$item],$open-1)[0]['availability_state']==='not_open','visible before opening');
    $hidden=example($end,true);
    check(OpenFabLab_Relay::visible_catalogue([$hidden],$open-1)===[],'hidden before opening');
    check(OpenFabLab_Relay::visible_catalogue([$hidden],$open)[0]['availability_state']==='available','opens exactly on cached snapshot');
    check(OpenFabLab_Relay::visible_catalogue([$item],$t-1)[0]['availability_state']!=='ended','before end');
    check(OpenFabLab_Relay::visible_catalogue([$item],$t)[0]['availability_state']==='ended','exact end');
    check(OpenFabLab_Relay::visible_catalogue([$item],$t+86399)[0]['availability_state']==='ended','before 24 elapsed hours');
    check(OpenFabLab_Relay::visible_catalogue([$item],$t+86400)===[],'exact 24 hours removed');
    check(OpenFabLab_Relay::visible_catalogue([$item],$t+86401)===[],'after 24 hours removed');
    $future=example(gmdate('c',$t+86400));$future['service_id']=2;
    $sorted=OpenFabLab_Relay::visible_catalogue([$item,$future],$t);
    check(array_column($sorted,'service_id')===[2,1],'ended below all upcoming');
    check(!isset($sorted[0]['publication']),'private timing projection not leaked');
    $slot=$future;$slot['booking_mode']='slots';$slot['slots']=[['slot_uuid'=>'fictif','available'=>1,'waiting'=>0,'waiting_limit'=>2,'starts_at'=>gmdate('c',$t+100),'ends_at'=>gmdate('c',$t+200)]];
    check(OpenFabLab_Relay::visible_catalogue([$slot],$t)[0]['slots'][0]['availability_state']==='available','slot open');
    check(OpenFabLab_Relay::visible_catalogue([$slot],$t+100)[0]['slots'][0]['availability_state']==='closed','slot exact closure');
}
$legacy=['service_id'=>3,'availability_state'=>'available','available'=>1,'slots'=>[]];
check(OpenFabLab_Relay::visible_catalogue([$legacy],0)===[$legacy],'old core payload unchanged');
echo json_encode(['success'=>true,'checks'=>count($checks),'executed'=>$checks],JSON_PRETTY_PRINT)."\n";
