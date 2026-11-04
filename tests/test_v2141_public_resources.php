<?php
// Reuse the existing no-network WP projection fixture, not a genuine WP database.
require __DIR__.'/test_v214_wordpress.php';
$initial=$checks;
check(isset($shortcodes['openfablab_resources']),'compatible resource alias registered');
$html=$shortcodes['openfablab_resources'](['environment'=>'test','category'=>'machine']);
check(str_contains($html,'data-environment="test"')&&str_contains($html,'data-category="machine"'),'alias preserves environment and category');
check($shortcodes['openfablab_resources'](['category'=>'<script>'])==='','invalid category never broadens the requested listing');
foreach (['public.js','public.css','translations.js'] as $file) {
 $found=array_filter($assets,fn($entry)=>str_ends_with($entry[1]??'','/'.$file));
 check(count($found)>0&&array_reduce($found,fn($ok,$entry)=>$ok&&$entry[3]===substr(hash_file('sha256',dirname(__DIR__).'/wordpress/openfablab-reservations/assets/'.$file),0,12),true),'public asset cache key matches actual bytes '.$file);
}
$snapshot['machines'][0]['category']='Machine';$snapshot['machines'][0]['category_key']='machine';
$snapshot['calendar'][0]['description']='Description publique fictive';$snapshot['calendar'][0]['capacity']=8;
$slot=['start'=>$snapshot['calendar'][0]['start'],'end'=>$snapshot['calendar'][0]['end'],'capacity'=>3,'availability_state'=>'waiting','close_at'=>$snapshot['calendar'][0]['close_at']];
$snapshot['calendar'][0]['slots']=[$slot];
check(OpenFabLab_Public::valid_snapshot($snapshot),'public descriptions, resource categories and slot-specific capacity accepted');
foreach(['email','participants','notes','secret','actor'] as $key){$bad=$snapshot;$bad['calendar'][0]['slots'][0][$key]='FAKE_PRIVATE';check(!OpenFabLab_Public::valid_snapshot($bad),'slot rejects private field '.$key);}
foreach([-1,'3',100001,null] as $value){$bad=$snapshot;$bad['calendar'][0]['slots'][0]['capacity']=$value;check(!OpenFabLab_Public::valid_snapshot($bad),'invalid slot capacity refused');}
$snapshot['calendar'][]=['id'=>'openlab-average','kind'=>'openlab','title'=>'OpenLab','start'=>'2026-12-01T14:00:00+01:00','end'=>'2026-12-01T18:00:00+01:00',
 'attendance_average'=>['users'=>8,'visitors'=>4,'since'=>'2026-05-01','until'=>'2026-10-31','method'=>'observed_same_weekday_hours_26w_v1']];
check(OpenFabLab_Public::valid_snapshot($snapshot),'aggregate average with explicit method and period accepted');
foreach(['users_raw','user_ids','sessions','emails','sample'] as $key){$bad=$snapshot;$bad['calendar'][1]['attendance_average'][$key]=[];check(!OpenFabLab_Public::valid_snapshot($bad),'raw aggregate detail prohibited '.$key);}
$bad=$snapshot;$bad['calendar'][1]['attendance_average']['users']=1;check(!OpenFabLab_Public::valid_snapshot($bad),'public mean below safety threshold refused');
$options['openfablab_public_snapshot_production']=['data'=>$snapshot,'received_at'=>time()];
$first=OpenFabLab_Public::read('machines','production')->data;
$snapshot['machines'][0]['name']='Ressource historique fictive mise à jour';
update_option('openfablab_public_snapshot_production',['data'=>$snapshot,'received_at'=>time()]);
$second=OpenFabLab_Public::read('machines','production')->data;
check($first['items'][0]['name']!==$second['items'][0]['name'],'read endpoint reflects replacement snapshot, not old cached rows');
check(OpenFabLab_Public::read('machines','test') instanceof WP_Error,'Normal replacement never populates Test');
$snapshot['machines']=[];update_option('openfablab_public_snapshot_production',['data'=>$snapshot,'received_at'=>time()]);
check(OpenFabLab_Public::read('machines','production')->data['items']===[],'genuine empty catalogue remains success, not a synchronization error');
echo ($checks-$initial)." complementary public-resource PHP checks passed\n";
