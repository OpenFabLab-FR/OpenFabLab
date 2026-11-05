<?php
// Actual receiver and reader, fictitious in-memory WordPress options only.
function wp_json_encode($value){return json_encode($value);}
class WP_REST_Response {public $headers=[];function __construct(public $data){}function header($name,$value){$this->headers[$name]=$value;}}
require __DIR__.'/test_wordpress_transport.php';
$initial=$checks;
$options['openfablab_public_machines_enabled']='1';
$base=['version'=>1,'timezone'=>'Europe/Paris','coverage_start'=>'2026-11-01','coverage_end'=>'2027-01-01','calendar'=>[]];
$machine=['id'=>'machine-fictional','name'=>'Machine fictive 2','status'=>'rental_available','reason'=>'','return_estimate'=>null];
$payload=['environment'=>'production','animations'=>[],'protocol_version'=>4,'relay_revision'=>3,'public_data'=>$base+['machines'=>[$machine]]];
$request=new WP_REST_Request;$request->body=json_encode($payload);
check(OpenFabLab_Relay::catalogue($request)['ok']===true,'receiver accepts rental availability');
check(count(OpenFabLab_Public::read('machines','production')->data['items'])===1,'public rental item available');
$test=$payload;$test['environment']='test';$request->body=json_encode($test);
check(OpenFabLab_Relay::catalogue($request)['ok']===true,'independent Test catalogue accepted');
$payload['public_data']['machines']=[];$request->body=json_encode($payload);
check(OpenFabLab_Relay::catalogue($request)['ok']===true,'replacement acknowledges unpublished item');
check(OpenFabLab_Public::read('machines','production')->data['items']===[],'receiver replaces snapshot instead of retaining removed resource');
check(count(OpenFabLab_Public::read('machines','test')->data['items'])===1,'Normal replacement never purges Test');
check(OpenFabLab_Public::read('machines','production')->headers['Cache-Control']==='no-store','public reads bypass browser cache');
check($options['openfablab_res_sync_secret']===str_repeat('f',64),'shared secret untouched');
echo ($checks-$initial)." resource catalogue replacement checks passed\n";
